import time
import sys
import os
import signal
import re

from DiagnosisSystemClass import DiagnosisSystemClass
from RandomDiagnoser import RandomDiagnoser

# List of diagnoser classes to test
DIAGNOSERS = [
    ("Random", RandomDiagnoser),
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

# Main execution
if __name__ == "__main__":
    modelsDir = os.path.expanduser("~/git/dxc25synth/data/weak")
    dataDir = os.path.expanduser("~/git/dxc25synth/data/dxc-09-syn-benchmark-1.1")
    
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
