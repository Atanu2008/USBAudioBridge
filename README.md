

# USBAudioBridge

### Stream Your PC Audio to Your Mobile and Listen Through Your Mobile Speaker

USBAudioBridge allows you to stream your **PC's audio to your Android phone through a USB connection** and play the audio using your phone's speaker.

---

## 🚀 Getting Started

### 1. Download the Mobile App

Download the **USBAudioBridge mobile app**:

[Download Mobile App](https://drive.google.com/file/d/1Yv4mccMp_2ihFsZuHUmgygA3y04oJhbZ/view?usp=sharing&utm_source=chatgpt.com)

---

### 2. Download ADB Platform Tools

Download **Android SDK Platform Tools** from the official Android Developer website:

[Download ADB Platform Tools](https://developer.android.com/tools/releases/platform-tools?utm_source=chatgpt.com)

Extract the downloaded ZIP file to a convenient location.

---

### 3. Connect Your Android Phone

1. Connect your Android phone to your PC using a **USB cable**.
2. Enable **Developer Options** on your phone.
3. Enable **USB Debugging**.
4. If your phone asks for permission to allow USB debugging, tap **Allow**.

---

### 4. Open Command Prompt

Open the folder where you extracted **ADB Platform Tools**.

Press:

**`Ctrl + L` → type `cmd` → press Enter**

A Command Prompt window will open in that folder.

---

### 5. Check Your Device

Run:

```cmd
adb devices
```

You should see your phone's **Device ID** in the list.

Example:

```text
List of devices attached
XXXXXXXX    device
```

> If your device shows **unauthorized**, check your phone and allow USB debugging.

---

### 6. Create the USB Port Forwarding

Run:

```cmd
adb reverse tcp:9999 tcp:9999
```

Then verify the connection:

```cmd
adb reverse --list
```

You should see something similar to:

```text
UsbFfs tcp:9999 tcp:9999
```

This means the USB connection is successfully forwarding port **9999** between your PC and phone.

---

### 7. Start the PC Server

Download the **`main.py`** [https://github.com/Atanu2008/USBAudioBridge/blob/main/main.py]file and run it on your PC.

Once the application opens:

**Press `START SERVER`**

Keep the application running while using USBAudioBridge.

---

### 8. Start the Mobile App

Open the **USBAudioBridge** app on your Android phone.

Press:

**`START`**

---

# 🎉 You're Done!

If everything is configured correctly, your **PC audio will now be streamed to your Android phone**, and you can listen to it through your **mobile speaker**.

### Connection Flow

```text
        PC
         │
         │ USB Cable
         ▼
   ADB USB Reverse
         │
         ▼
     Android App
         │
         ▼
   Mobile Speaker 🔊
```

> **Tip:** You need to keep USB debugging enabled and the USB connection active while using USBAudioBridge.
> **NOTE:**Don't kill the adb terminal . 
