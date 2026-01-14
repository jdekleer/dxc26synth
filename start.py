#!/usr/bin/env python3
"""
start.py - Entry point for your diagnoser submission.

Competitors: Modify this file to import and register your diagnoser.
Do NOT modify RunDiagnoser.py.

Usage:
    python3 start.py --ag                      # Run on all models
    python3 start.py --ag --model 74L85        # Run on specific model
    python3 start.py --ag --results out.csv    # Save results to CSV
"""

from RunDiagnoser import run_main

# =============================================================================
# Import your diagnoser here
# =============================================================================
# from MyDiagnoser import MyDiagnoser

# For demonstration, we import the example diagnosers
from DiagnosisSystemClass import DiagnosisSystemClass  # SimpleSingleFault baseline


# =============================================================================
# Register your diagnoser(s) here
# =============================================================================
# Format: list of (name, class) tuples
# The name is used in output/results

DIAGNOSERS = [
    # Add your diagnoser here:
    # ("MyTeamDiagnoser", MyDiagnoser),
    
    # Example baseline (you can remove this):
    ("SimpleSingleFault", DiagnosisSystemClass),
]


# =============================================================================
# Run the benchmark - do not modify below this line
# =============================================================================
if __name__ == "__main__":
    run_main(DIAGNOSERS)

