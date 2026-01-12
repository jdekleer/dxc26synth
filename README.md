# Competition Setup Guide

This is a preliminary guide to running the Synthetic track competition environment.  It will evolve as we proceed.

You can get this repository from https://github.com/jdekleer/dxc26synth.git 

The simplest way to run the diagnoser is to go to the directory you installed dxc26synth.git and do python3 RunDiagnoser.py.

For example, python3 RunDiagnoser.py --ag --model 74L85 will run the diagnostic algorithm on all scenarios in the 74L85 data set.  The --ag flag indicates the metric that will be used for the competition.

This repository comes with several baseline diagnosers built-in.  You should see output like this:

```
################################################################################
# Running AG Benchmark: Null
################################################################################

  74L85.xml (33 gates): ............................
==========================================================================================
AG Benchmark Results for: Null
==========================================================================================
Model        Gates    Avg m_utl    Evaluated    Skipped    DA T/O  
------------------------------------------------------------------------------------------
74L85        33       0.6573       28           0          0       
==========================================================================================

################################################################################
# Running AG Benchmark: Random
################################################################################

  74L85.xml (33 gates): ............................
==========================================================================================
AG Benchmark Results for: Random
==========================================================================================
Model        Gates    Avg m_utl    Evaluated    Skipped    DA T/O  
------------------------------------------------------------------------------------------
74L85        33       0.6608       28           0          0       
==========================================================================================

################################################################################
# Running AG Benchmark: Worst
################################################################################

  74L85.xml (33 gates): ............................
==========================================================================================
AG Benchmark Results for: Worst
==========================================================================================
Model        Gates    Avg m_utl    Evaluated    Skipped    DA T/O  
------------------------------------------------------------------------------------------
74L85        33       0.0040       28           0          0       
==========================================================================================

################################################################################
# Running AG Benchmark: SimpleSingleFault
################################################################################

  74L85.xml (33 gates): ............................
==========================================================================================
AG Benchmark Results for: SimpleSingleFault
==========================================================================================
Model        Gates    Avg m_utl    Evaluated    Skipped    DA T/O  
------------------------------------------------------------------------------------------
74L85        33       0.7488       28           0          0       
==========================================================================================
```

**Column meanings:**
- **Avg m_utl**: Normalized utility metric (1.0 = perfect, 0.0 = worst)
- **Evaluated**: Number of scenarios processed
- **Skipped**: Scenarios skipped (ground truth unavailable)
- **DA T/O**: DA timeouts (penalized with score 0)

**How m_utl is calculated:**

The metric compares the DA's ambiguity group (D) against the true ambiguity group (T):

1. For each pair of diagnoses (ω ∈ D, ω* ∈ T), compute:
   ```
   m_utl(ω, ω*) = 1 - n(N+1)/f(n+1) - n̄(N̄+1)/f(n̄+1)
   ```
   where n = false positives, n̄ = false negatives, N = |ω|, N̄ = f - N, f = total components.

2. Average over all pairs: `m_utl(D,T) = avg over all (ω, ω*) pairs`

3. Normalize by the best achievable score: `m̃_utl = m_utl(D,T) / m_utl(T,T)`

This ensures a perfect match (D = T) scores 1.0.



**Built-in Diagnosers:**

- **Null**: Always reports "nothing wrong" (no detection, empty isolation). Baseline that never makes false positive accusations but misses all faults.

- **Random**: Always detects a fault and returns a random single gate. Baseline for comparison.

- **Worst**: Returns a single diagnosis claiming ALL gates are faulty simultaneously. This maximizes false positives and scores near 0.

- **SimpleSingleFault**: Simulates the circuit and finds all single-gate faults consistent with observations. A reasonable baseline that achieves ~75% on 74L85.

The benchmark files come from past DXC competitions run in 2009, 2010 and 2011.  The model files used are exactly the same as well.  We are providing you examples of simple diagnosers which show you how to parse these model files.

The final score of a DA is m_utl averaged over all designs, and the score for a design is the average of the m_utl's of all its scenarios.  The competition gives you 1 second for each scenario file.  Obtaining
a perfect score in that time is very challenging.  We do not expect any algorithm will be able to get a perfect score.  For each benchmark scenario we have computed the minimum cardinality ambiguity group for each scenario.  We provide the DXC scenario files so you can see the correct ambiguity group for each scenario.  The highest scores are obtained by a DA which can find the correct minimum cardinality and all the diagnoses of that group.

For the final competition we will have a completely new set of scenario files which we will run on one of our machines.


To define your own diagnoser.  Look at RunDiagnoser.py, in the beginning of the file you will see a variable DIAGNOSERS=... Just look at one of the diagnoser definitions and you can see how to implement your own.  And add it to DIAGNOSERS as shown.

Please note that all solutions will be evaluated inside a docker image created with the provided docker file. Please ensure that all precomputed files are compatible with this environment. It is strongly recommended that you run your final model training on the docker image created using the provided dockerfile.

Example how to save and load models and scalers is provided in ExampleDiagnosisSystem.py. Please make sure that your solution includes trained models (where applicable) in the data/resources directory and the source code required to train the models.


## Prerequisites
- [Docker](https://docs.docker.com/get-docker/) installed on your machine (instructions provided below).
- Git installed to clone the repository.

### Docker Installation

#### Ubuntu
1. **Update your system**:
   ```bash
   sudo apt update
   ```

2. **Install Docker**:
   ```bash
   sudo apt install docker.io
   ```

3. **Start and Enable Docker**:
   ```bash
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

4. **Add your user to the Docker group** (optional, for running Docker without `sudo`):
   ```bash
   sudo usermod -aG docker $USER
   ```
   After this, log out and log back in for changes to take effect.

#### Windows
1. **Download Docker Desktop** from [Docker's official website](https://www.docker.com/products/docker-desktop).
2. **Install Docker Desktop** and follow the on-screen instructions.
3. **Enable WSL2 Integration** (recommended):
   - Open Docker Desktop settings.
   - Navigate to "Resources" > "WSL Integration" and enable integration for your desired WSL2 distributions.
4. **Verify Installation**:
   Open PowerShell or Command Prompt and run:
   ```powershell
   docker --version
   ```

## Repository Setup
1. **Clone the Repository**:
   ```bash
   get this repository from https://github.com/jdekleer/dxc26synth.git 
   ```


## Running the Environment

### Build the Docker Image

In the directory where the Dockerfile is located, build the Docker image:

```bash
docker build -t competition_env .
```

### Running the Evaluation

To run the evaluation, mount the current directory and specify input file. The output file is saved in the results directory with the output_ prefix.

#### Ubuntu
```bash
docker run -v "$(pwd):/app" --network none competition_env RunDiagnoser.py data/training_data/wltp_NF.csv 
```

#### Windows (PowerShell)

```powershell
docker run -v "${PWD}:/app" --network none competition_env RunDiagnoser.py data/training_data/wltp_NF.csv
```


By using --network none, the container will be completely isolated from the network, ensuring it cannot connect to the internet or any external network.

## Command-Line Arguments

```
python3 RunDiagnoser.py [options]
```

| Argument | Description |
|----------|-------------|
| `--ag` | Run AG benchmark with normalized m_utl metric (required for competition scoring) |
| `--model MODEL` | Filter to a specific model (e.g., `--model 74L85`) |
| `--scenarios PATH` | Path to benchmark scenarios directory. Defaults to `data/DXC26Synth1` |
| `--results PATH` | Output results to a CSV file with per-model scores and final weighted average |

**Examples:**

```bash
# Run full AG benchmark on all models
python3 RunDiagnoser.py --ag

# Run only the 74L85 benchmark
python3 RunDiagnoser.py --ag --model 74L85

# Use custom scenarios directory and save results to CSV
python3 RunDiagnoser.py --ag --scenarios ~/my_scenarios --results benchmark_results.csv

# Run on specific scenarios and export results
python3 RunDiagnoser.py --ag --model c432 --results c432_results.csv
```

The `--results` CSV file contains:
- Per-model rows: Diagnoser, Model, Gates, Avg_m_utl, Evaluated, Skipped, DA_Timeouts
- Final score summary: Weighted average m_utl across all designs for each diagnoser

