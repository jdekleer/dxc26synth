import time
import sys
import os
import signal
import re

from DiagnosisSystemClass import DiagnosisSystemClass

# Timeout for processing each .scn file (in seconds)
SCN_TIMEOUT = 1

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Processing exceeded timeout")

def parse_fault_injection(line):
    """Parse faultInjection line and return set of faulty gates."""
    # Format: faultInjection @5000 isInjection = true, fault = { gate72 = faulty }, parameters = {};
    # Can have multiple faults: fault = { gate72 = faulty, gate73 = faulty }
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

# Set up signal handler
signal.signal(signal.SIGALRM, timeout_handler)

## Create diagnosis system class
EDS = DiagnosisSystemClass()

## Initialize diagnosis system
EDS.Initialize()

modelsDir = os.path.expanduser("~/git/dxc25synth/data/weak")
dataDir = os.path.expanduser("~/git/dxc25synth/data/dxc-09-syn-benchmark-1.1")

# Results storage
model_results = {}

for modelFile in os.listdir(modelsDir):
    if modelFile.endswith('.xml'):
        EDS.newModelFile(os.path.join(modelsDir, modelFile))
        print(f"\n{modelFile} ({len(EDS.gates)} gates): ", end="", flush=True)
        modelName = modelFile.replace('.xml', '')
        modelDataDir = os.path.join(dataDir, modelName)
        
        detection_times = []  # Time to detection for each .scn file
        isolation_scores = []  # Isolation score for each .scn file
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
                    # Set timeout for this .scn file
                    signal.alarm(SCN_TIMEOUT)
                    scn_start_time = time.time()
                    
                    with open(dataFilePath, 'r') as f:
                        for line in f:
                            line = line.strip()
                            
                            # Check for fault injection
                            if line.startswith('faultInjection'):
                                fault_injected = True
                                injected_faults = parse_fault_injection(line)
                                samples_after_fault = 0
                                continue
                            
                            if line.startswith('sensors'):
                                # Parse: sensors @timestamp { key1 = value1, key2 = value2, ... };
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
                                    
                                    detection, isolation = EDS.Input(sensors, timeout=SCN_TIMEOUT, start_time=scn_start_time)
                                    last_isolation = isolation
                                    
                                    # Track time to detection after fault injection
                                    if fault_injected:
                                        if detection and time_to_detection is None:
                                            time_to_detection = samples_after_fault
                                        samples_after_fault += 1
                    
                    # Cancel the alarm
                    signal.alarm(0)
                    
                except TimeoutError:
                    print(f"  TIMEOUT: {dataFile} exceeded {SCN_TIMEOUT}s")
                    signal.alarm(0)  # Cancel the alarm
                    timed_out = True
                
                # Record time to detection for this .scn file
                if timed_out:
                    detection_times.append(float('inf'))
                    isolation_scores.append(0)
                    num_timeouts += 1
                elif time_to_detection is not None:
                    detection_times.append(time_to_detection)
                    
                    # Compute isolation score
                    if len(injected_faults) == 1:
                        # Single fault - check if it's in the isolation set
                        injected_fault = list(injected_faults)[0]
                        if injected_fault in last_isolation:
                            isolation_scores.append(1)
                        else:
                            isolation_scores.append(0)
                    else:
                        # Multiple faults - score 0 for now
                        isolation_scores.append(0)
                elif fault_injected:
                    # Fault was injected but never detected
                    detection_times.append(float('inf'))
                    isolation_scores.append(0)
                
                # Progress dot
                print(".", end="", flush=True)
        
        # Compute averages for this model
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

# Print results
print("\n" + "="*80)
print("Diagnosis Results")
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
