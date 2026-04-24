# Install the Six-Window Shortcut (⌘⇧1)

One button on the Mac → six Ghostty windows open, each SSHed into the
DGX running one of the seats from `lab/SEATS.md`.

You do this once. After that, every time you hit ⌘⇧1 you get your
full operator console.

---

## What you need

- A Mac with Ghostty installed.
- SSH working to the DGX. Test it first: open Terminal, type
  `ssh spark` and hit return. If you get a prompt on the DGX, you're
  set. If not, fix SSH first (talk to Claude).

---

## Step-by-step (takes 5 minutes)

**1.** Open Terminal on the Mac. Go to your polysignal-engine
checkout. The path is wherever you do `git clone` — probably
`~/code/polysignal-engine` or `~/Documents/polysignal-engine`.

```
cd ~/code/polysignal-engine    # change path if yours is different
```

**2.** Pull the latest changes (this grabs tonight's work):

```
git pull origin main
```

**3.** Copy the script into a folder the Mac can always find:

```
mkdir -p ~/.local/bin
cp lab/ghostty-shortcut/polysignal-seats.sh ~/.local/bin/
```

**4.** Mark the script as runnable:

```
chmod +x ~/.local/bin/polysignal-seats.sh
```

**5.** Test it from Terminal (sanity check, no shortcut yet):

```
~/.local/bin/polysignal-seats.sh
```

Six Ghostty windows should pop up. Each one SSHes into the DGX and
starts its seat. Close them all when you're done testing — the next
step makes them come back with one keystroke.

**6.** Open macOS Shortcuts.app. The fastest way: press `⌘Space`,
type `Shortcuts`, hit return.

**7.** In Shortcuts, click the `+` button (top-right) to make a new
shortcut. Give it a name like `PolySignal Seats`.

**8.** In the search bar on the right side of the Shortcuts editor,
type `Run Shell Script`. Drag the **Run Shell Script** action into
the middle of the window.

**9.** In the shell script box that just appeared, delete whatever is
there and paste in exactly this (replace `YOUR-MAC-USERNAME` with
your Mac username — find it by running `whoami` in Terminal):

```
/Users/YOUR-MAC-USERNAME/.local/bin/polysignal-seats.sh
```

**10.** Just below the shell script box, set:
- **Shell:** `/bin/bash`
- **Input:** `no input` (default is fine)
- **Pass Input:** `to stdin` is OK, won't matter

**11.** In the top-right of the shortcut editor, click the slider
icon (looks like sliders) to open "Details". Find the
**Add Keyboard Shortcut** button. Click it, then press `⌘⇧1`
(Command + Shift + 1) on your keyboard. The shortcut should show
up as `⌘⇧1`.

**12.** Close the shortcut editor. The shortcut saves automatically.

**13.** Press `⌘⇧1` anywhere on your Mac. Six Ghostty windows
should appear.

If you want them in specific screen positions, drag each one where
you want it — macOS remembers window positions per app and will
reopen them roughly in place next time.

---

## If it doesn't work

**Six windows open but all of them say "Operation timed out" or
"No route to host":** You're off home network (airport, hotspot,
coffee shop). SSH can't reach the LAN IP. Fix:

1. Open `~/.local/bin/polysignal-seats.sh` in any text editor.
2. Find the line `SSH_HOST="spark"` near the top.
3. Change it to `SSH_HOST="dgx-remote"` — that routes through the
   Cloudflare Tunnel which works from anywhere.
4. Save. Try `⌘⇧1` again.

**Only some windows open, or Ghostty says "unknown option
--command":** Your Ghostty might be an older version that uses a
different flag. Check Ghostty's help:
`/Applications/Ghostty.app/Contents/MacOS/ghostty --help`. If
`--command` isn't listed, try `-e` instead. Edit the script's
`open_seat` function to swap the flag.

**Shortcut fires but nothing happens:** Open the Shortcuts app, run
the shortcut once from there (click the play button). The error
message shows up in the editor. Usually it's a wrong path in step 9
— your username isn't `YOUR-MAC-USERNAME`, it's whatever `whoami`
printed.

**One window shows "truth board — write lab/truth_board.py":** That's
expected. The Truth Board seat falls back to a placeholder until
`lab/truth_board.py` gets written (Session 42). When it exists, the
script auto-switches to running it.

---

## What each window shows

| # | Window title | What it shows |
|---|---|---|
| 1 | `polysignal/1-fire` | Active watchdog alerts + the last 5 scanner events |
| 2 | `polysignal/2-scanner` | Live scanner log (new cycle every 5 min) |
| 3 | `polysignal/3-truth` | Accuracy + last-100 real-trade winrate (placeholder until Session 42) |
| 4 | `polysignal/4-brain` | `brain/memory.md` open in your editor — **write here** |
| 5 | `polysignal/5-loop` | Loop's current session: model, cost, token burn, last heartbeat |
| 6 | `polysignal/6-vitals` | GPU temps, disk, systemd service status |

Full rationale for each seat lives in `lab/SEATS.md`.
