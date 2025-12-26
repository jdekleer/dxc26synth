import time
import sys
import os
import signal
import re

from DiagnosisSystemClass import DiagnosisSystemClass
# Add more diagnosers here:
# from MyBetterDiagnoser import MyBetterDiagnoser
# from NeuralDiagnoser import NeuralDiagnoser

# List of diagnoser classes to test
DIAGNOSERS = [
    ("SimpleSingleFault", DiagnosisSystemClass),
    # ("BetterDiagnoser", MyBetterDiagnoser),
    # ("NeuralDiagnoser", NeuralDiagnoser),
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
            print(f"\n  {modelFile} ({len(EDS.gates)} gates): ", end="", flush=True)
            modelName = modelFile.replace('.xml', '')
            modelDataDir = os.path.join(dataDir, modelName)
            
            detection_times = []
            isolation_scores = []
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
                        num_timeouts += 1
                    elif time_to_detection is not None:
                        detection_times.append(time_to_detection)
                        
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
                    
                    print(".", end="", flush=True)
            
            if detection_times:
                finite_times = [t for t in detection_times if t != float('inf')]
                if finite_times:
                    avg_time = sum(finite_times) / len(finite_times)
                else:
                    avg_time = float('inf')
                num_detected = len(finite_times)
                num_total = len(detection_times)
                
                if isolation_scores:
                    avg_isolation = sum(isolation_scores) / len(isolation_scores)
                else:
                    avg_isolation = 0
                
                model_results[modelName] = {
                    'avg_time_to_detection': avg_time,
                    'num_detected': num_detected,
                    'num_total': num_total,
                    'num_timeouts': num_timeouts,
                    'avg_isolation_score': avg_isolation
                }
    
    return model_results

def print_results(diagnoser_name, model_results):
    """Print results for a diagnoser."""
    print("\n" + "="*80)
    print(f"Results for: {diagnoser_name}")
    print("="*80)
    print(f"{'Model':<15} {'Avg TTD':<10} {'Detected':<10} {'Total':<8} {'Timeouts':<10} {'Avg Isol':<10}")
    print("-"*80)
    
    for model in sorted(model_results.keys()):
        result = model_results[model]
        avg = result['avg_time_to_detection']
        avg_str = f"{avg:.2f}" if avg != float('inf') else "N/A"
        isol_str = f"{result['avg_isolation_score']:.2f}"
        print(f"{model:<15} {avg_str:<10} {result['num_detected']:<10} {result['num_total']:<8} {result['num_timeouts']:<10} {isol_str:<10}")
    
    print("="*80)

def print_comparison(all_results):
    """Print comparison table across all diagnosers."""
    if len(all_results) <= 1:
        return
    
    print("\n" + "="*100)
    print("COMPARISON ACROSS DIAGNOSERS")
    print("="*100)
    
    # Get all models
    all_models = set()
    for diagnoser_name, results in all_results.items():
        all_models.update(results.keys())
    
    # Header
    header = f"{'Model':<15}"
    for diagnoser_name in all_results.keys():
        header += f" {diagnoser_name[:12]:<14}"
    print(header)
    print("-"*100)
    
    # Rows (showing avg isolation score)
    for model in sorted(all_models):
        row = f"{model:<15}"
        for diagnoser_name, results in all_results.items():
            if model in results:
                isol = results[model]['avg_isolation_score']
                row += f" {isol:.2f}         "
            else:
                row += " N/A          "
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
