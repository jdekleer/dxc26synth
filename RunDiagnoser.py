import time
import sys
import os
import signal
import re

from DiagnosisSystemClass import DiagnosisSystemClass
from RandomDiagnoser import RandomDiagnoser, NullDiagnoser, WorstDiagnoser

# List of diagnoser classes to test
DIAGNOSERS = [
    ("Null", NullDiagnoser),
    ("Random", RandomDiagnoser),
    ("Worst", WorstDiagnoser),
    ("SimpleSingleFault", DiagnosisSystemClass),
]

# Timeout for processing each .scn file (in seconds)
SOFT_TIMEOUT = 1   # Internal timeout (method should check this)
HARD_TIMEOUT = 2   # External timeout (signal alarm - kills if method doesn't obey)

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Processing exceeded timeout")

def parse_fault_injection(line):
    """Parse faultInjection line and return set of faulty gates."""
    match = re.search(r'fault\s*=\s*\{([^}]*)\}', line)
    if match:
        fault_content = match.group(1)
        faults = set()
        for pair in fault_content.split(','):
            pair = pair.strip()
            if '=' in pair:
                gate_name = pair.split('=')[0].strip()
                faults.add(gate_name)
        return faults
    return set()


def parse_ambiguity_group(line):
    """Parse ambiguityGroup line and return set of frozensets (the AG).
    
    Format: ambiguityGroup @7000 size = 2, minCardinality = 1, diagnoses = { { gate107 }, { gate97 } };
    Or multi-fault: diagnoses = { { gate101, gate106 }, { gate103, gate106 }, ... };
    
    Returns None if timeout or invalid format.
    """
    if 'timeout' in line.lower():
        return None
    
    # Find the diagnoses part
    match = re.search(r'diagnoses\s*=\s*\{(.+)\}\s*;', line)
    if not match:
        return None
    
    diagnoses_str = match.group(1).strip()
    
    # Parse individual diagnoses: { gate1, gate2 }, { gate3 }, ...
    ag = set()
    # Find all { ... } blocks
    diagnosis_matches = re.findall(r'\{([^}]*)\}', diagnoses_str)
    
    for diag_str in diagnosis_matches:
        gates = set()
        for gate in diag_str.split(','):
            gate = gate.strip()
            if gate:
                gates.add(gate)
        if gates:
            ag.add(frozenset(gates))
    
    return ag if ag else None


def parse_scn_file_for_ag(filepath):
    """Read a .scn file and extract the true ambiguity group.
    
    Returns:
        tuple: (sensor_readings, true_ag, num_components_hint)
        sensor_readings: list of dicts with sensor values
        true_ag: set of frozensets representing the true AG, or None if timeout
    """
    sensor_readings = []
    true_ag = None
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            
            if line.startswith('sensors'):
                start = line.find('{')
                end = line.find('}')
                if start != -1 and end != -1:
                    content = line[start+1:end].strip()
                    sensors = {}
                    for pair in content.split(','):
                        pair = pair.strip()
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            sensors[key] = (value == 'true')
                    sensor_readings.append(sensors)
            
            elif line.startswith('ambiguityGroup'):
                true_ag = parse_ambiguity_group(line)
    
    return sensor_readings, true_ag


def run_ag_benchmark(diagnoser_class, modelsDir, dataDir, model_filter=None):
    """Run benchmark using ambiguity groups and normalized m_utl metric.
    
    Args:
        diagnoser_class: The diagnoser class to test
        modelsDir: Directory containing model XML files
        dataDir: Directory containing .scn scenario files (DXC26Synth1 format)
        model_filter: Optional model name to run only that model (e.g., '74L85')
    
    Returns:
        dict: Results per model
    """
    # Set up signal handler
    signal.signal(signal.SIGALRM, timeout_handler)
    
    # Create diagnosis system
    EDS = diagnoser_class()
    EDS.Initialize()
    
    # Results storage
    model_results = {}
    
    for modelFile in os.listdir(modelsDir):
        if modelFile.endswith('.xml'):
            modelName = modelFile.replace('.xml', '')
            
            # Filter by model name if specified
            if model_filter and modelName != model_filter:
                continue
            
            EDS.newModelFile(os.path.join(modelsDir, modelFile))
            num_gates = len(EDS.gates)
            print(f"\n  {modelFile} ({num_gates} gates): ", end="", flush=True)
            modelDataDir = os.path.join(dataDir, modelName)
            
            # Metrics storage
            mutl_scores = []
            num_skipped = 0
            num_processed = 0
            
            if os.path.isdir(modelDataDir):
                dataFiles = sorted(os.listdir(modelDataDir))
                for dataFile in dataFiles:
                    if not dataFile.endswith('.scn'):
                        continue
                    
                    dataFilePath = os.path.join(modelDataDir, dataFile)
                    
                    # Parse the .scn file
                    sensor_readings, true_ag = parse_scn_file_for_ag(dataFilePath)
                    
                    # Skip scenarios where ground truth AG is unavailable (timed out during data generation)
                    # We can't evaluate the DA if we don't know the correct answer
                    if true_ag is None:
                        num_skipped += 1
                        print("s", end="", flush=True)  # s = skipped (no ground truth)
                        continue
                    
                    try:
                        signal.alarm(HARD_TIMEOUT)
                        scn_start_time = time.time()
                        
                        # Feed all sensor readings to the DA
                        da_isolation = set()
                        for sensors in sensor_readings:
                            detection, isolation = EDS.Input(sensors, timeout=SOFT_TIMEOUT, start_time=scn_start_time)
                            if detection and isolation:
                                da_isolation = isolation
                        
                        signal.alarm(0)
                        
                        # Convert DA's isolation to an AG (set of frozensets)
                        # Check if DA already returned AG format (set of frozensets) or old format (set of strings)
                        if da_isolation:
                            first_elem = next(iter(da_isolation))
                            if isinstance(first_elem, frozenset):
                                # Already AG format
                                da_ag = da_isolation
                            else:
                                # Old format: each gate is a singleton diagnosis
                                da_ag = {frozenset({gate}) for gate in da_isolation}
                        else:
                            # If no isolation, use empty diagnosis (will score poorly)
                            da_ag = {frozenset()}
                        
                        # Compute normalized m_utl
                        score = mutl_normalized(da_ag, true_ag, num_gates)
                        mutl_scores.append(score)
                        num_processed += 1
                        print(".", end="", flush=True)
                        
                    except TimeoutError:
                        signal.alarm(0)
                        # Penalize DA timeouts with score = 0
                        mutl_scores.append(0.0)
                        num_processed += 1
                        print("t", end="", flush=True)  # t = timeout in DA
            
            if mutl_scores:
                avg_mutl = sum(mutl_scores) / len(mutl_scores)
                num_da_timeouts = sum(1 for s in mutl_scores if s == 0.0)
                model_results[modelName] = {
                    'avg_mutl_normalized': avg_mutl,
                    'num_processed': num_processed,
                    'num_skipped': num_skipped,      # no ground truth available
                    'num_da_timeouts': num_da_timeouts,  # DA timed out (penalized with 0)
                    'num_gates': num_gates
                }
    
    return model_results


def print_ag_results(diagnoser_name, model_results):
    """Print results for AG benchmark."""
    print("\n" + "="*90)
    print(f"AG Benchmark Results for: {diagnoser_name}")
    print("="*90)
    print(f"{'Model':<12} {'Gates':<8} {'Avg m_utl':<12} {'Evaluated':<12} {'Skipped':<10} {'DA T/O':<8}")
    print("-"*90)
    
    for model in sorted(model_results.keys()):
        r = model_results[model]
        print(f"{model:<12} {r['num_gates']:<8} {r['avg_mutl_normalized']:.4f}       {r['num_processed']:<12} {r['num_skipped']:<10} {r['num_da_timeouts']:<8}")
    
    print("="*90)

def run_benchmark(diagnoser_class, modelsDir, dataDir):
    """Run benchmark on a single diagnoser class and return results."""
    
    # Set up signal handler
    signal.signal(signal.SIGALRM, timeout_handler)
    
    # Create diagnosis system
    EDS = diagnoser_class()
    EDS.Initialize()
    
    # Results storage
    model_results = {}
    
    for modelFile in os.listdir(modelsDir):
        if modelFile.endswith('.xml'):
            EDS.newModelFile(os.path.join(modelsDir, modelFile))
            num_gates = len(EDS.gates)
            print(f"\n  {modelFile} ({num_gates} gates): ", end="", flush=True)
            modelName = modelFile.replace('.xml', '')
            modelDataDir = os.path.join(dataDir, modelName)
            
            # Metrics storage
            detection_times = []
            isolation_scores = []       # 1 if fault in isolation set, 0 otherwise
            isolation_sizes = []        # Size of isolation set
            false_positives = 0         # Detection before fault injection
            true_negatives = 0          # No detection before fault injection
            num_timeouts = 0
            
            if os.path.isdir(modelDataDir):
                dataFiles = sorted(os.listdir(modelDataDir))
                for idx, dataFile in enumerate(dataFiles):
                    dataFilePath = os.path.join(modelDataDir, dataFile)
                    
                    fault_injected = False
                    injected_faults = set()
                    samples_after_fault = 0
                    time_to_detection = None
                    timed_out = False
                    last_isolation = set()
                    
                    try:
                        signal.alarm(HARD_TIMEOUT)
                        scn_start_time = time.time()
                        
                        with open(dataFilePath, 'r') as f:
                            for line in f:
                                line = line.strip()
                                
                                if line.startswith('faultInjection'):
                                    fault_injected = True
                                    injected_faults = parse_fault_injection(line)
                                    samples_after_fault = 0
                                    continue
                                
                                if line.startswith('sensors'):
                                    start = line.find('{')
                                    end = line.find('}')
                                    if start != -1 and end != -1:
                                        content = line[start+1:end].strip()
                                        sensors = {}
                                        for pair in content.split(','):
                                            pair = pair.strip()
                                            if '=' in pair:
                                                key, value = pair.split('=', 1)
                                                key = key.strip()
                                                value = value.strip()
                                                sensors[key] = (value == 'true')
                                        
                                        detection, isolation = EDS.Input(sensors, timeout=SOFT_TIMEOUT, start_time=scn_start_time)
                                        last_isolation = isolation
                                        
                                        # Track false positives (detection before fault)
                                        if not fault_injected:
                                            if detection:
                                                false_positives += 1
                                            else:
                                                true_negatives += 1
                                        
                                        # Track detection after fault injection
                                        if fault_injected:
                                            if detection and time_to_detection is None:
                                                time_to_detection = samples_after_fault
                                            samples_after_fault += 1
                        
                        signal.alarm(0)
                        
                    except TimeoutError:
                        signal.alarm(0)
                        timed_out = True
                    
                    if timed_out:
                        detection_times.append(float('inf'))
                        isolation_scores.append(0)
                        isolation_sizes.append(0)
                        num_timeouts += 1
                    elif time_to_detection is not None:
                        detection_times.append(time_to_detection)
                        isolation_sizes.append(len(last_isolation))
                        
                        if len(injected_faults) == 1:
                            injected_fault = list(injected_faults)[0]
                            if injected_fault in last_isolation:
                                isolation_scores.append(1)
                            else:
                                isolation_scores.append(0)
                        else:
                            isolation_scores.append(0)
                    elif fault_injected:
                        detection_times.append(float('inf'))
                        isolation_scores.append(0)
                        isolation_sizes.append(0)
                    
                    print(".", end="", flush=True)
            
            if detection_times:
                finite_times = [t for t in detection_times if t != float('inf')]
                if finite_times:
                    avg_time = sum(finite_times) / len(finite_times)
                else:
                    avg_time = float('inf')
                num_detected = len(finite_times)
                num_total = len(detection_times)
                
                # Detection accuracy (true positive rate)
                detection_accuracy = num_detected / num_total if num_total > 0 else 0
                
                # False positive rate
                total_pre_fault = false_positives + true_negatives
                fp_rate = false_positives / total_pre_fault if total_pre_fault > 0 else 0
                
                # Isolation metrics
                if isolation_scores:
                    avg_isolation = sum(isolation_scores) / len(isolation_scores)
                else:
                    avg_isolation = 0
                
                if isolation_sizes:
                    avg_isolation_size = sum(isolation_sizes) / len(isolation_sizes)
                else:
                    avg_isolation_size = 0
                
                model_results[modelName] = {
                    'avg_time_to_detection': avg_time,
                    'num_detected': num_detected,
                    'num_total': num_total,
                    'num_timeouts': num_timeouts,
                    'detection_accuracy': detection_accuracy,
                    'false_positive_rate': fp_rate,
                    'avg_isolation_score': avg_isolation,
                    'avg_isolation_size': avg_isolation_size,
                    'num_gates': num_gates
                }
    
    return model_results

def print_results(diagnoser_name, model_results):
    """Print results for a diagnoser."""
    print("\n" + "="*120)
    print(f"Results for: {diagnoser_name}")
    print("="*120)
    print(f"{'Model':<12} {'Gates':<8} {'Det Acc':<10} {'FP Rate':<10} {'Avg TTD':<10} {'Isol Score':<12} {'Isol Size':<10} {'Timeouts':<10}")
    print("-"*120)
    
    for model in sorted(model_results.keys()):
        r = model_results[model]
        avg_ttd = f"{r['avg_time_to_detection']:.2f}" if r['avg_time_to_detection'] != float('inf') else "N/A"
        print(f"{model:<12} {r['num_gates']:<8} {r['detection_accuracy']:.2f}      {r['false_positive_rate']:.2f}      {avg_ttd:<10} {r['avg_isolation_score']:.2f}        {r['avg_isolation_size']:.1f}       {r['num_timeouts']:<10}")
    
    print("="*120)

def print_comparison(all_results):
    """Print comparison table across all diagnosers."""
    if len(all_results) <= 1:
        return
    
    diagnoser_names = list(all_results.keys())
    
    # Get all models
    all_models = set()
    for diagnoser_name, results in all_results.items():
        all_models.update(results.keys())
    
    # Comparison: Isolation Score
    print("\n" + "="*100)
    print("COMPARISON: Isolation Score (higher is better)")
    print("="*100)
    header = f"{'Model':<15}"
    for name in diagnoser_names:
        header += f" {name[:15]:<17}"
    print(header)
    print("-"*100)
    for model in sorted(all_models):
        row = f"{model:<15}"
        for name in diagnoser_names:
            if model in all_results[name]:
                val = all_results[name][model]['avg_isolation_score']
                row += f" {val:.2f}             "
            else:
                row += " N/A              "
        print(row)
    print("="*100)
    
    # Comparison: Isolation Size
    print("\n" + "="*100)
    print("COMPARISON: Isolation Size (smaller is better - more precise)")
    print("="*100)
    header = f"{'Model':<15}"
    for name in diagnoser_names:
        header += f" {name[:15]:<17}"
    print(header)
    print("-"*100)
    for model in sorted(all_models):
        row = f"{model:<15}"
        for name in diagnoser_names:
            if model in all_results[name]:
                val = all_results[name][model]['avg_isolation_size']
                row += f" {val:.1f}             "
            else:
                row += " N/A              "
        print(row)
    print("="*100)
    
    # Comparison: False Positive Rate
    print("\n" + "="*100)
    print("COMPARISON: False Positive Rate (lower is better)")
    print("="*100)
    header = f"{'Model':<15}"
    for name in diagnoser_names:
        header += f" {name[:15]:<17}"
    print(header)
    print("-"*100)
    for model in sorted(all_models):
        row = f"{model:<15}"
        for name in diagnoser_names:
            if model in all_results[name]:
                val = all_results[name][model]['false_positive_rate']
                row += f" {val:.2f}             "
            else:
                row += " N/A              "
        print(row)
    print("="*100)

# =============================================================================
# Normalized m_utl metric for Ambiguity Groups (from DXMetrics paper)
# =============================================================================
#
# Base formula for single diagnoses:
#   m_utl(ω,ω*) = 1 - n(N+1)/f(n+1) - n̄(N̄+1)/f(n̄+1)
#
# where:
#   n = |ω - ω*|  (false positives: diagnosed but not faulty)
#   N = |ω|       (size of diagnosis)
#   n̄ = |ω* - ω|  (false negatives: missed faults)
#   N̄ = f - N     (size of complement)
#
# For ambiguity groups, we average over all pairs and normalize by the best
# achievable score (when D = T).

def mutl_single(omega, omega_star, f):
    """
    Compute m_utl for a single diagnosis pair.
    
    Args:
        omega: frozenset of diagnosed faulty components
        omega_star: frozenset of true faulty components
        f: total number of components in the system
    
    Returns:
        m_utl score in [0, 1]
    """
    n = len(omega - omega_star)      # false positives
    N = len(omega)                   # diagnosis size
    nbar = len(omega_star - omega)   # false negatives
    Nbar = f - N                     # complement size
    
    term1 = (n * (N + 1)) / (f * (n + 1))
    term2 = (nbar * (Nbar + 1)) / (f * (nbar + 1))
    
    return 1 - term1 - term2


def mutl_ag(D, T, f):
    """
    Compute average m_utl over all pairs from two ambiguity groups.
    
    Args:
        D: set of frozensets - diagnosis AG from the DA
        T: set of frozensets - true AG
        f: total number of components in the system
    
    Returns:
        average m_utl score
    """
    total = sum(mutl_single(omega, omega_star, f)
                for omega in D for omega_star in T)
    return total / (len(D) * len(T))


def mutl_normalized(D, T, f):
    """
    Compute normalized m_utl for ambiguity groups.
    
    Normalizes by the best achievable score (when D = T), so that
    a perfect match yields a score of 1.
    
    Args:
        D: set of frozensets - diagnosis AG from the DA
        T: set of frozensets - true AG  
        f: total number of components in the system
    
    Returns:
        normalized m_utl score in [0, 1], where 1 = perfect match
    """
    score = mutl_ag(D, T, f)
    best = mutl_ag(T, T, f)
    return score / best


# Convenience alias for backward compatibility
def mutl(w, wstar, f):
    """
    Compute m_utl for single diagnosis sets (backward compatible).
    
    Args:
        w: set of diagnosed faulty components
        wstar: set of true faulty components
        f: total number of components
    
    Returns:
        m_utl score
    """
    return mutl_single(frozenset(w), frozenset(wstar), f)

# Main execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run diagnosis benchmarks')
    parser.add_argument('--ag', action='store_true', help='Run AG benchmark with normalized m_utl')
    parser.add_argument('--model', type=str, default=None, help='Filter to specific model (e.g., 74L85)')
    parser.add_argument('--datadir', type=str, default=None, help='Override data directory')
    args = parser.parse_args()
    
    modelsDir = os.path.expanduser("~/git/dxc25synth/data/weak")
    
    if args.ag:
        # AG benchmark with DXC26Synth1 format
        dataDir = args.datadir or os.path.expanduser("~/git/dxc25synth/data/DXC26Synth1")
        
        all_results = {}
        for diagnoser_name, diagnoser_class in DIAGNOSERS:
            print(f"\n{'#'*80}")
            print(f"# Running AG Benchmark: {diagnoser_name}")
            print(f"{'#'*80}")
            
            results = run_ag_benchmark(diagnoser_class, modelsDir, dataDir, model_filter=args.model)
            all_results[diagnoser_name] = results
            print_ag_results(diagnoser_name, results)
    else:
        # Original benchmark
        dataDir = args.datadir or os.path.expanduser("~/git/dxc25synth/data/dxc-09-syn-benchmark-1.1")
        
        all_results = {}
        for diagnoser_name, diagnoser_class in DIAGNOSERS:
            print(f"\n{'#'*80}")
            print(f"# Running: {diagnoser_name}")
            print(f"{'#'*80}")
            
            results = run_benchmark(diagnoser_class, modelsDir, dataDir)
            all_results[diagnoser_name] = results
            print_results(diagnoser_name, results)
        
        # Print comparison if multiple diagnosers
        print_comparison(all_results)
