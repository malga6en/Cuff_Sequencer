# Pneumatic Cuff Sequencer

A Python-based desktop application for configuring and executing pneumatic cuff inflation protocols via serial communication with a microcontroller.

The application provides an intuitive graphical user interface for controlling pneumatic cuff experiments, monitoring pressure in real time, logging measurement data, and automatically generating plots after each experiment.

<img width="668" height="450" alt="image" src="https://github.com/user-attachments/assets/329d0eac-6a41-4fb5-8104-fda401c3d2a1" />

---

## Features

- Serial communication with an Arduino-compatible microcontroller
- Configurable inflation/deflation protocols
- Multiple protocol presets (A, B, C)
- Live pressure visualization
- Real-time pressure display
- Automatic CSV data logging
- Automatic pressure plot generation
- Support for pressure input in **bar** or **mmHg**
- Experiment log window
- Integrated user guide

---

## Screenshots

<img width="1000" height="750" alt="image" src="https://github.com/user-attachments/assets/46cb88dc-c48b-4d7d-bc69-db7db09bceb8" />

---

## Requirements

- Python 3.10 or newer

Required packages:

```bash
pyserial
matplotlib
pillow
```

---

# Setup

## 1. Clone the Repository

```bash
git clone https://github.com/malga6en/Cuff_Sequencer.git

or

download Zip
```

---

## 2. Create a Python Virtual Environment

I use VS Code as Coding Environment...

### Windows - Terminal

```bash
python -m venv .venv
```

Activate the virtual environment:

```bash
.venv\Scripts\activate
```

### Linux / macOS - Terminal

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After activation you should see something similar to:

```text
(.venv)
```

at the beginning of your terminal.

---

## 3. Install Dependencies

Install all required packages:

```bash
pip install -r requirements.txt
```

Verify the installation:

```bash
pip list
```

---

## 4. Run the Application

Start the GUI:

```bash
python cuff_app.py
```

---

# Building an Executable (Windows)

Install PyInstaller:

```bash
pip install pyinstaller
```

Build a standalone executable:

```bash
pyinstaller --onefile --noconsole --icon=Sport.jpeg --add-data "FHWN.png;." --add-data "Sport.jpeg;." --add-data "Technik.jpeg;." cuff_app.py
```

The executable will be created in:

```text
dist/
└── cuff_app.exe
```

---

# Updating the Requirements File

If additional Python packages are installed, update the requirements file:

```bash
pip freeze > requirements.txt
```

---

# Project Structure

```text
Pneumatic-Cuff-Sequencer/
│
├── cuff_app.py
├── requirements.txt
├── README.md
├── LICENSE
│
├── FHWN.png
├── Sport.jpeg
├── Technik.jpeg
│
├── build/
├── dist/
└── .venv/
```

---

## Pressure Units

The GUI supports two display units:

- bar
- mmHg

Switching between units only affects the graphical interface.

Internally, all communication with the microcontroller continues to use **bar**, therefore **no firmware changes are required**.

---

## Data Logging

For every completed experiment the software automatically creates:

- CSV file containing all recorded measurements
- PNG plot of the pressure profile

CSV columns:

- Date
- Time
- Protocol
- Time [ms]
- Phase
- ADC value
- Pressure [bar]

---

## Communication Protocol

The software communicates with the microcontroller via a serial interface.

Example command:

```
RUN <inflate_voltage> <deflate_voltage> <inflate_time_ms> <deflate_time_ms> <repetitions>
```

Example:

```
RUN 1.700 0.000 5000 5000 5
```

Incoming data format:

```
DATA,<time_ms>,<phase>,<adc>,<pressure_bar>
```

Example:

```
DATA,1250,INFLATE,2354,0.182
```

---

## License

This project is licensed under the MIT License.

See the LICENSE file for details.

---

## Author

**Mustafa Algan**

University of Applied Sciences Wiener Neustadt (FHWN)

Department of Robotics and AI
