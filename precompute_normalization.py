#!/usr/bin/env python3
"""
Precompute normalization factors for .scn files.

For each .scn file with an ambiguity group, computes mutl_ag(T, T, f)
and appends it to the file. This avoids recomputing during benchmark runs.

If computation takes > 30 seconds, uses sampling and marks as approximate.
"""

import os
import sys
import time
import signal

# Import the mutl functions
from RunDiagnoser import (
    parse_ambiguity_group, 
    mutl_ag_vectorized, 
    mutl_ag_sampled,
    mutl_ag
)

TIMEOUT_SECONDS = 30

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Computation exceeded timeout")

def compute_normalization(true_ag, f):
    """
    Compute mutl_ag(T, T, f) with timeout.
    
    Returns:
        (value, is_approximate) tuple
    """
    num_pairs = len(true_ag) ** 2
    
    # For small AGs, compute directly
    if num_pairs < 1000:
        total = 0.0
        from RunDiagnoser import mutl_single
        for omega in true_ag:
            for omega_star in true_ag:
                total += mutl_single(omega, omega_star, f)
        return total / num_pairs, False
    
    # For larger AGs, use vectorized with timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)
    
    try:
        result = mutl_ag_vectorized(true_ag, true_ag, f)
        signal.alarm(0)
        return result, False
    except TimeoutError:
        signal.alarm(0)
        # Fall back to sampling
        print(f"  Timeout after {TIMEOUT_SECONDS}s, using sampling...", end="", flush=True)
        result = mutl_ag_sampled(true_ag, true_ag, f, num_samples=50000)
        return result, True
    except MemoryError:
        signal.alarm(0)
        print(f"  OOM, using sampling...", end="", flush=True)
        result = mutl_ag_sampled(true_ag, true_ag, f, num_samples=50000)
        return result, True


def process_scn_file(filepath, f):
    """
    Process a single .scn file and add normalization factor.
    
    Returns: (success, was_already_done, is_approximate)
    """
    with open(filepath, 'r') as file:
        content = file.read()
    
    # Check if already has normalization factor
    if 'normalizationFactor' in content:
        return True, True, False
    
    # Find the ambiguity group line
    lines = content.strip().split('\n')
    ag_line = None
    ag_line_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith('ambiguityGroup'):
            ag_line = line.strip()
            ag_line_idx = i
            break
    
    if ag_line is None:
        return False, False, False
    
    # Parse the AG
    true_ag = parse_ambiguity_group(ag_line)
    if true_ag is None:
        # Timeout in data
        return False, False, False
    
    # Compute normalization factor
    norm_value, is_approximate = compute_normalization(true_ag, f)
    
    # Create the normalization line
    approx_str = ", approximate = true" if is_approximate else ""
    norm_line = f"normalizationFactor = {norm_value:.10f}{approx_str};"
    
    # Append to file
    with open(filepath, 'a') as file:
        file.write(f"\n{norm_line}\n")
    
    return True, False, is_approximate


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Precompute normalization factors')
    parser.add_argument('--model', type=str, default=None, help='Process only this model')
    parser.add_argument('--datadir', type=str, 
                        default=os.path.expanduser("~/git/dxc25synth/data/DXC26Synth1"),
                        help='Data directory')
    parser.add_argument('--modelsdir', type=str,
                        default=os.path.expanduser("~/git/dxc25synth/data/weak"),
                        help='Models directory')
    args = parser.parse_args()
    
    # Use DiagnosisSystemClass to get gate counts (same as benchmark)
    from DiagnosisSystemClass import DiagnosisSystemClass
    ds = DiagnosisSystemClass()
    ds.Initialize()
    
    gate_counts = {}
    for model_file in os.listdir(args.modelsdir):
        if model_file.endswith('.xml'):
            model_name = model_file.replace('.xml', '')
            ds.newModelFile(os.path.join(args.modelsdir, model_file))
            gate_counts[model_name] = len(ds.gates)
    
    print(f"Found {len(gate_counts)} models")
    
    # Process each model
    for model_name in sorted(gate_counts.keys()):
        if args.model and model_name != args.model:
            continue
        
        model_dir = os.path.join(args.datadir, model_name)
        if not os.path.isdir(model_dir):
            continue
        
        f = gate_counts[model_name]
        print(f"\n{model_name} ({f} gates):")
        
        scn_files = sorted([f for f in os.listdir(model_dir) if f.endswith('.scn')])
        
        for scn_file in scn_files:
            filepath = os.path.join(model_dir, scn_file)
            print(f"  {scn_file}: ", end="", flush=True)
            
            start = time.time()
            success, already_done, is_approx = process_scn_file(filepath, f)
            elapsed = time.time() - start
            
            if already_done:
                print("already done")
            elif not success:
                print("skipped (no AG or timeout)")
            elif is_approx:
                print(f"approximate ({elapsed:.1f}s)")
            else:
                print(f"exact ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()

