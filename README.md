# Pneumatic Cuff Sequencer

A Python-based desktop application for configuring and executing pneumatic cuff inflation protocols via serial communication with a microcontroller.

The application provides an intuitive graphical user interface for controlling pneumatic cuff experiments, monitoring pressure in real time, logging measurement data, and automatically generating plots after each experiment.

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

*(Add screenshots here)*

---

## Requirements

- Python 3.10 or newer

Required packages:

```bash
pip install pyserial matplotlib pillow
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/<username>/Pneumatic-Cuff-Sequencer.git
cd Pneumatic-Cuff-Sequencer
```

Install dependencies:

```bash
pip install -r requirements.txt
```

or

```bash
pip install pyserial matplotlib pillow
```

---

## Running the Application

```bash
python cuff_app.py
```

---

## Creating an Executable

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller --onefile --noconsole ^
--add-data "FHWN.png;." ^
--add-data "Sport.jpeg;." ^
--add-data "Technik.jpeg;." ^
cuff_app.py
```

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

## Pressure Units

The GUI supports two display units:

- bar
- mmHg

Switching between units only affects the graphical interface.

Internally, all communication with the microcontroller continues to use **bar**, therefore **no firmware changes are required**.

---

## Project Structure

```
.
├── cuff_app.py
├── FHWN.png
├── Sport.jpeg
├── Technik.jpeg
├── README.md
└── LICENSE
```

---

## Dependencies

- Python
- Tkinter
- PySerial
- Matplotlib
- Pillow

---

## License

This project is licensed under the MIT License.

See the LICENSE file for details.

---

## Author

**Mustafa Algan**

University of Applied Sciences Wiener Neustadt (FHWN)

Department of Robotics and Mechatronics
