# Secure Cloud Deduplication Using Proof of Ownership (PoW)

A Python implementation of a **Proof of Ownership (PoW) protocol for secure cloud deduplication**, featuring adaptive block-size selection, file integrity verification, and performance benchmarking.

The project investigates how block size affects proof-generation and verification performance across different file sizes and evaluates whether adaptive block-size selection is worthwhile.

## Overview

Cloud storage providers often receive duplicate copies of the same file from multiple users. Deduplication avoids storing redundant copies, reducing storage requirements.

However, deduplication introduces a security challenge: a malicious user who knows a file's identifier should not be able to claim ownership without possessing the actual file.

This project implements a Proof of Ownership mechanism in which a client must demonstrate possession of a file before receiving deduplication benefits.

It also benchmarks different block sizes to identify performance trade-offs and implements an adaptive selector that calibrates candidate block sizes before choosing one.

## Key Features

- **Proof of Ownership:** Generates and verifies cryptographic proofs using SHA-256.
- **Secure Deduplication Demo:** Demonstrates file registration, ownership verification, and rejection of an unauthorized ownership claim.
- **Adaptive Block-Size Selection:** Measures candidate block sizes and selects one based on calibration results.
- **Fixed Block-Size Mode:** Allows performance comparison against a predefined block size.
- **File Integrity:** Uses a cryptographic file tag to identify file content.
- **Challenge-Based Verification:** Uses a fresh, single-use challenge with an expiration time.
- **Block-Size Binding:** Binds the challenge seed to the selected block size.
- **Performance Benchmarking:** Measures proof-generation time, verification time, throughput, and statistical variation.
- **Automated Tests:** Includes correctness and security-oriented tests.
- **Results and Visualization:** Exports CSV files, plots, and a Markdown benchmark report.
- **Optional Firebase Registry:** Supports Firebase Realtime Database as an alternative to the local JSON registry.

## Technology Stack

- Python 3.8+
- SHA-256 (`hashlib`)
- HMAC-based pseudorandom generation
- File processing and cryptographic verification
- CSV-based benchmark analysis
- Matplotlib (optional, for plots)
- Firebase Admin SDK (optional, for the Firebase registry)

## Project Structure

```text
pow_project/
├── adaptive.py              # Adaptive block-size calibration and selection
├── benchmark.py             # Performance experiments and result generation
├── main.py                  # End-to-end demonstration
├── pow_core.py              # Core PoW algorithm and file processing
├── proof.py                 # Compatibility wrapper
├── protocol.py               # Client-server verification protocol
├── registry.py               # Local and optional Firebase registries
├── server.py                 # Server compatibility wrapper
├── run_tests.py              # Correctness and security-oriented tests
├── requirements.txt          # Optional dependencies
├── .gitignore                # Files excluded from Git
└── results/
    ├── results_adaptive.csv
    ├── results_raw.csv
    ├── results_summary.csv
    ├── results_plot_t1.png
    └── results_report.md
```

## How the System Works

1. **File Identification:** The system computes a cryptographic tag for the file.
2. **Deduplication Check:** The registry determines whether the file has already been registered.
3. **Block-Size Selection:** The client either uses a fixed block size or calibrates candidate sizes using a sample of the file.
4. **Challenge Generation:** The server issues a fresh challenge seed.
5. **Proof Generation:** The client generates a proof using the file contents, challenge seed, and selected block size.
6. **Proof Verification:** The server independently computes the expected proof and compares the results.
7. **Ownership Registration:** A successful verification allows the user to be recorded as an owner of the existing file.

The included demonstration simulates these interactions locally. It does not require a deployed cloud server.

## Adaptive Block-Size Selection

Different block sizes can produce different performance results.

- Small blocks require more iterations and repeated processing operations.
- Larger blocks reduce the number of iterations but may introduce other processing costs.
- The optimal block size depends on the implementation and execution environment.

The adaptive selector benchmarks candidate sizes and chooses a size based on their measured performance.

The implementation uses a sample of the file, repeated calibration rounds, a median-based timing estimate, and a tolerance relative to the fastest candidate. The selector also caches results to avoid repeating calibration unnecessarily.

The project supports both:

- **Fixed selection:** Use a predefined block size.
- **Adaptive selection:** Calibrate and select a block size automatically.

This makes it possible to evaluate whether the potential performance improvement justifies the calibration overhead.

## Experiments and Evaluation

### Experiment 1: File-Size Impact

Investigates how increasing file size affects proof-generation and verification time.

### Experiment 2: Block-Size Sensitivity

Compares multiple block sizes to identify their effect on generation time, verification time, and throughput.

### Experiment 3: Performance Across File Sizes

Evaluates block-size performance for 50 MB, 100 MB, and 200 MB files to examine whether the observed performance trends persist as file size increases.

### Experiment 4: Adaptive Selector Evaluation

Evaluates the adaptive selection strategy using:

- **Regret:** The generation time at the selected block size divided by the generation time at the best measured block size.
- **Calibration cost:** The time required to evaluate candidate block sizes.
- **Break-even point:** The number of proof generations needed for the time saved by the selected size to compensate for the calibration overhead.

These experiments help distinguish the fastest measured fixed configuration from the practical value of choosing a block size adaptively.

## Benchmark Results

In the recorded block-size sweep, the measured generation times were:

| File Size | Best Tested Block Size | Mean Generation Time |
|---|---:|---:|
| 50 MB | 256 KB | 0.0396 s |
| 100 MB | 256 KB | 0.0798 s |
| 200 MB | 256 KB | 0.1606 s |

For these runs, **256 KB achieved the lowest measured generation time among the tested block sizes**.

The adaptive selector usually chose 128 KB and occasionally chose 256 KB in the recorded trials. Its mean regret was approximately 1.04 across the three file sizes, indicating that its chosen configuration was close to the best measured configuration in those trials.

However, calibration took approximately 0.73–0.74 seconds in these measurements. Whether adaptive selection is worthwhile therefore depends on how frequently proofs are generated and which fixed block size is used as the baseline.

These results are specific to the recorded environment and should not be interpreted as universally optimal settings.

Detailed measurements and generated tables are available in `results/results_report.md` and the accompanying CSV files.

## Installation

### Prerequisites

- Python 3.8 or later
- Git (optional, for cloning the repository)

### 1. Clone the repository

```bash
git clone https://github.com/arjunvashishtha13/cloud-deduplication-pow.git
cd cloud-deduplication-pow
```

### 2. Create a virtual environment (recommended)

Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can still run Python using `.venv\Scripts\python.exe`.

### 3. Install optional dependencies

The core implementation uses Python's standard library. Optional dependencies are needed for plotting or Firebase integration.

For plots:

```bash
pip install matplotlib
```

For Firebase integration:

```bash
pip install firebase-admin
```

## Running the Project

### 1. Run the tests

```bash
python run_tests.py
```

Run this first to check the project's correctness and security-oriented test cases.

### 2. Run the demonstration

```bash
python main.py
```

The demo illustrates:

- Alice uploading a file for the first time.
- Bob presenting the same file and being verified.
- Mallory attempting to claim ownership using a known tag but a different file.

The demo runs locally and creates its working files in `demo_run/`.

### 3. Use a custom file

```bash
python main.py --file path/to/your_file.bin
```

The supplied file must contain at least two bytes.

### 4. Use a fixed block size

```bash
python main.py --fixed-kb 256
```

This skips adaptive calibration and uses the specified block size.

### 5. Run the benchmark suite

```bash
python benchmark.py
```

By default, the benchmark evaluates 50 MB, 100 MB, and 200 MB files, multiple block sizes, and repeated runs.

### 6. Run a quick benchmark

```bash
python benchmark.py --quick
```

Use this for a shorter smoke test rather than the full evaluation.

### 7. Run a custom benchmark

```bash
python benchmark.py --sizes 50 100 --blocks 16 64 128 256 512 --runs 10
```

This evaluates selected file sizes and block sizes with 10 runs per setting.

Additional benchmark options include thread counts, implementation variants, adaptive calibration trials, and output paths. Run:

```bash
python benchmark.py --help
```

for the supported arguments.

## Output Files

The benchmark generates machine-readable and human-readable results, including:

- Raw measurements
- Aggregated performance summaries
- Adaptive-selector results
- Performance plots
- A Markdown report with benchmark findings

Check the generated report before using its measurements in a research paper or presentation.

## Limitations

- The current client-server demonstration runs locally rather than across a real network.
- Benchmark timings depend on the machine, operating system, Python implementation, and system load.
- The recorded measurements do not establish performance on every cloud platform or hardware configuration.
- The adaptive selector introduces calibration overhead that may not be worthwhile for infrequent proof generation.
- Local benchmark results alone do not establish the absence of all security vulnerabilities.
- A production deployment would require additional work on network communication, authentication, access control, operational monitoring, and secure secret management.

## Future Work

Potential extensions include:

- Testing on real cloud infrastructure.
- Evaluating larger files and additional block sizes.
- Measuring network communication overhead.
- Investigating CPU and energy consumption.
- Comparing implementations across hardware platforms.
- Improving adaptive calibration to reduce overhead.
- Evaluating concurrent clients and larger workloads.

## Security Notes

- Never commit Firebase service-account credentials, API keys, passwords, or other secrets.
- Keep sensitive configuration files outside public repositories.
- The included Firebase integration is optional; the default demonstration uses a local registry.
- Do not treat this research prototype as a production-ready cloud storage security service.

## License

No license has been specified yet. Add a license before explicitly permitting others to reuse or redistribute this project.
