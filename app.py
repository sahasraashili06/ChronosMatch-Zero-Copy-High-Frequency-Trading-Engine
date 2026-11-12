
import streamlit as st
import subprocess
import sys
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_DIR = BASE_DIR / "python"

st.set_page_config(
    page_title="ChronosMatch HFT Dashboard",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ ChronosMatch")
st.subheader("Zero-Copy High-Frequency Trading Engine")
st.caption("Python Edition | Academic Project Demo")

st.divider()

c1, c2, c3 = st.columns(3)
c1.metric("Automated Tests", "374 / 374")
c2.metric("Code Coverage", "85%")
c3.metric("Previous Throughput", "42,407 ops/sec")

st.divider()

st.subheader("Trading Engine Simulation")

if st.button("▶ Start Simulation", type="primary"):
    with st.spinner("Running actual ChronosMatch simulator..."):
        try:
            result = subprocess.run(
                [sys.executable, "main.py"],
                cwd=PYTHON_DIR,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                st.success("Simulation completed successfully!")
            else:
                st.error("Simulation execution failed.")

            output = result.stdout or "No output available."

            match = re.search(
                r"Rate\s*:\s*~?([\d,]+)\s+orders/sec",
                output
            )

            if match:
                st.metric(
                    "Measured Throughput",
                    match.group(1) + " orders/sec"
                )

            st.subheader("Actual Simulator Output")
            st.code(output)

            if result.stderr:
                with st.expander("Error details"):
                    st.code(result.stderr)

        except subprocess.TimeoutExpired:
            st.error("Simulation exceeded 60 seconds.")

        except Exception as error:
            st.exception(error)

st.divider()
st.subheader("Project Verification")
st.write("Last verified automated tests: 374 passed.")
st.write("Last measured code coverage: 85%.")
st.caption("ChronosMatch | Academic Demonstration")
