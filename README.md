# FH6-AutoRacer

## *An automation tool for Forza Horizon 6 races. It drives, restarts and farms events for you while you're away.(SMART MACRO)*


> 📣 **RELEASE V.1.0.0.BETA** 📣
>
> 🏁 **Race Modes**
>  * **Online Races** — joins the event, picks the car, drives and keeps going race after race.
>  * **Standard / EventLab Races** — drives, then auto-restarts the event from the results screen.
>  * **Rivals** — endless laps on the same route, counting every completed lap.
>  * **TimeAttack** — endless laps, counting each one as it crosses the line.
>
> 🔍 **Detection & Lap Counting**
>  * Laps are counted by **reading the lap timer digits**, not by matching an image: the counter is reliable no matter how long the lap is.
>  * The Time Attack timer is read **only when it's white**, so the green/red checkpoint splits can never trigger a false lap.
>  * **Anti-inactivity**: detects the "Inactivity Detected" warning and clears it automatically, so you never get kicked from the session.
>  * **Diagnostic Mode** for matches, to avoid blindly modifying thresholds when using different settings (like HDR or custom templates).
>
> ⚙️ **Driving**
>  * **Manual shifting** (optional): shifts up when the gear digit hits the rev limiter and shifts down by reading the RPM bar. Requires manual transmission enabled in FH6 and digital Speedometer.
>  * **Auto-focus**: brings the game back to the foreground if it loses focus, and pauses the inputs while it isn't focused.
>
> 🛑 **Auto-Stop & Notifications**
>  * Stop automatically after a number of **races/laps** or after a number of **minutes**.
>  * Optional **sound** and **Windows toast** notification when the limit is reached.
>  * Every completed race is logged to a **CSV file** with timestamp and total.
>
> 🖥️ **UI & Multi-Language Support**
>  * Clean overlay with live **status**, **race/lap counter**, **active time** gauge and an in-app **Log** page.
>  * **Customization Page** in the settings: overlay language, in-game language, live overlay resize and full color theming.
>  * Four languages currently available: **English, Italian, Spanish and German** (WIP ONLY ENGLISH IT'S AVAILABLE IN BETA).
>
> ⚙️ **Total Customization**
>  * No hardcoded limits: match thresholds, key timings, polling and timeouts are all adjustable from the overlay to match your PC.
>  * Fully reworked **Keybinds**.
>
> 🛠️ **Coming Next**
>  * **Colossus farm** is built and ready but currently **disabled**, since the event was patched. It will be re-enabled as soon as a new route is found.
>  * **Templates in other languages** other game languages templates coming soon.
>
> ⚙️ **Requirements and settings**
>
> * Windows **10 or 11**
> * Resolution **4k/2k/1080p/720p** (16:9)
> * UI size **100%**
> * Graphics preset **Very Low**
> * Braking **Assisted**
> * Steering **Auto-Steering**
> * Shifting **Manual** (optional)(only if you enable manual shifting)
>
> ▶️ **How to use**
>
>  **Step 1 – Pick your race**
> - Launch Forza Horizon 6 and get to the event you want to farm.
> - **Online**: stop on the event registration screen.
> - **Standard/EventLab**: stop on the "Start Race Event" screen.
> - **Rivals / TimeAttack**: stop on the "Start Rivals Event" screen, or just start the tool while you're already driving.
>  **Step 2 – Configure the tool**
> - Run **AutoRacer.exe** as administrator. The overlay will appear on screen.
> - In **Races**, select the mode you're farming. Only one can be active at a time.
> - In **Settings**, set your **in-game language** (it decides which templates are loaded) and, if you want, enable **manual shifting** and **auto-stop**.
>  **Step 3 – Start**
> - Go back to FH6, press **F8** or **Start**, and let it run.
> - To stop: press **F8** again, **F9** for emergency stop, or click **STOP** on the overlay.
>
> 🛡️ **SmartScreen warning**
>
> Windows SmartScreen will show a warning because the exe is not digitally signed. To run it anyway:
> - Click **More info**
> - Click **Run anyway**
>
> ⚠️ **Warning**
>
> - *Automating races may violate the Forza Code of Conduct.*
> - *Results may vary depending on your PC and settings.*
> - *You risk a warning, a suspension or a permanent ban.*
> - *Use it at your own risk.*
