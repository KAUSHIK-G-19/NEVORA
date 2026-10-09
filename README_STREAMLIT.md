# NEVORA BMS Intelligence — Streamlit Dashboard

Interactive Web Dashboard & 800V Battery Pack Digital Twin powered by Physics-Informed Neural Networks (PINN).

---

## ⚡ Overview

This Streamlit application bridges the automotive embedded C++ core (`src/`) and the Physics-Informed Neural Network ONNX model (`nevora_pinn.onnx`) into a web-based Digital Twin:

- **Edge ONNX Runtime Inference**: Evaluates normalized pack inputs ($V/800$, $(I+1000)/2000$, $(T+40)/120$, $SoC/100$) in real-time.
- **Electrochemical Physics Validator**: Butler-Volmer kinetics constraint checker ($F = 96485.33$ C/mol, $R = 8.314$ J/mol·K).
- **Interactive Drive Modes**: DC Fast Charge (+120A), Dynamic Drive (-25A), Ludicrous Launch (-185A), Regenerative (+38A), Cell Balancer (-1.2A).
- **32-Cell Series-Parallel Matrix**: 4 Modules (MOD-A, MOD-B, MOD-C, MOD-D) with individual cell voltage, thermal gradient, and balancing indicators.
- **Fault Injection Simulation**: Demonstrates PINN early degradation and thermal anomaly detection on Cell #14 before hardware BMS trip.
- **CAN Bus Decoder**: Decodes simulated `0x18F00101` and `0x18F00201` frames.

---

## 💻 1. How to Run Locally

### Option A: 1-Click Launch (Windows)
Double-click:
```
run_streamlit.bat
```

### Option B: Terminal Command
Make sure your Python environment has the dependencies installed:
```bash
pip install -r requirements.txt
streamlit run app.py
```
Or with python launcher:
```bash
py -3.13 -m streamlit run app.py
```

The application will automatically open in your default browser at:
`http://localhost:8501`

---

## 🚀 2. Easy Cloud Deployment Options

### Method 1: Streamlit Community Cloud (Recommended & Free)
1. Commit and push the project repository to GitHub:
   ```bash
   git add .
   git commit -m "Add NEVORA Streamlit dashboard and deployment configs"
   git push origin main
   ```
2. Navigate to [share.streamlit.io](https://share.streamlit.io) and log in.
3. Click **"New app"**, select your GitHub repository, set branch to `main`, and main file path to:
   ```
   app.py
   ```
4. Click **"Deploy!"**. Streamlit will automatically install `requirements.txt`, load `nevora_pinn.onnx`, and provide a public URL.

---

### Method 2: Docker Container Deployment (AWS, GCP, Render, Azure)
A production-ready [Dockerfile](file:///c:/Users/KAUSHIK%20G/OneDrive/Desktop/innovate/Dockerfile) is included.

1. Build the Docker container image:
   ```bash
   docker build -t nevora-bms-twin .
   ```
2. Run the container:
   ```bash
   docker run -p 8501:8501 nevora-bms-twin
   ```
3. Access at `http://localhost:8501`.

---

### Method 3: Hugging Face Spaces
1. Create a new Space on [huggingface.co/spaces](https://huggingface.co/spaces).
2. Select **Streamlit** as the Space SDK.
3. Push your repository files (`app.py`, `nevora_pinn.onnx`, `nevora_pinn.onnx.data`, `requirements.txt`).
4. Hugging Face Spaces will build and host your app with GPU/CPU inference automatically!
