# PLC to Serial Dashboard Pro

A modern Graphical User Interface (GUI) application built with Python (Tkinter) designed to monitor states from a Mitsubishi PLC (via MC Protocol Type 3E) and automatically forward dynamic data strings (Dynamic Word Data) to a serial communication port (COM Port) in real-time.

The application is heavily optimized using **Multi-threading** to eliminate UI freezing, featuring an autonomous hardware reconnection manager and a secure Admin authentication layer.

---

## 🚀 Key Features

*   **Modern Dark Mode UI:** High-contrast, slick dark theme integrated with a responsive Progress Bar and explicit hardware LED status indicators (PLC / Serial).
*   **Dynamic Register Configuration:** Add or remove up to 10 configuration rows on-the-fly for custom data registers (`D8310`, `D8326`, etc.).
*   **Intelligent String Truncation:** Real-time positive/negative string trimming/truncating of the binary buffer decoded from the PLC before transmission over Serial.
*   **Secure Hardware Handshaking:** Seamlessly monitors the rising edge of the trigger bit (e.g., `M8010`), validates the `0x06 (ACK)` byte response from the Serial device, and automatically sets the complete flag bit (e.g., `M8011`).
*   **Anti-Freeze & Reconnect Flow:** 
    *   Decoupled architecture separating the hardware execution loop (Worker Thread) from the Main UI Thread.
    *   Robust internal socket error patching for `pymcprotocol` (fixing the `'Type3E' object has no attribute '_sock'` issue), ensuring graceful retries during power loss or cable disconnection.
*   **Admin Access Protection:** Requires an administrative password to stop monitoring or modify hardware settings, preventing unauthorized or accidental interactions by operators.
*   **Auto-save Config:** Seamlessly saves and reloads your last configuration parameters locally using a hidden JSON file under `%APPDATA%`.

---

## 🛠 Prerequisites & Installation

### 1. Environment Requirements
*   Python 3.x or higher installed.

### 2. Dependency Dependencies
Open your Terminal or Command Prompt and run the following command to install the required hardware communication libraries:

```bash
pip install pyserial pymcprotocol