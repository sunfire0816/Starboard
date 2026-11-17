"""
Experimental screen reader for scan signatures (Windows 10/11 only).

Uses the text recognition built into Windows (Windows.Media.Ocr) through
Windows PowerShell, so nothing extra has to be installed. One PowerShell
process runs in the background: it captures the screen area you picked,
enlarges it, reads it twice (as is, and as a cleaned-up high-contrast copy that
is never shown) and prints both readings. This module starts and stops that
process and hands each line of text to a callback.
"""

import os
import subprocess
import sys
import threading

PS_SCRIPT = r"""
param([int]$X, [int]$Y, [int]$W, [int]$H, [int]$IntervalMs = 700, [int]$Scale = 0)
$ErrorActionPreference = 'Stop'
try {
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class SCLDpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
    [void][SCLDpi]::SetProcessDPIAware()
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    function Await($op, [Type]$type) {
        $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
        [void]$task.Wait(-1)
        $task.Result
    }
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) { throw 'Windows text recognition is not available for your language.' }
    # enlarge small areas more (Windows reads up to 2600 pixels a side)
    if ($Scale -le 0) { $Scale = [Math]::Max(1, [Math]::Min(4, [Math]::Floor(2600 / [Math]::Max($W, $H)))) }
    # cleaned copy: gray, strong contrast, light text turned dark on white, then cut to pure black and white
    $c = 2.4; $o = 0.5 * ($c - 1)
    $cm = New-Object System.Drawing.Imaging.ColorMatrix(,[single[][]]@(
        [single[]]@(-0.299 * $c, -0.299 * $c, -0.299 * $c, 0, 0),
        [single[]]@(-0.587 * $c, -0.587 * $c, -0.587 * $c, 0, 0),
        [single[]]@(-0.114 * $c, -0.114 * $c, -0.114 * $c, 0, 0),
        [single[]]@(0, 0, 0, 1, 0),
        [single[]]@((1 + $o), (1 + $o), (1 + $o), 0, 1)))
    $attr = New-Object System.Drawing.Imaging.ImageAttributes
    $attr.SetColorMatrix($cm)
    $attr.SetThreshold(0.6)
    function ReadBitmap($b) {
        $ms = New-Object System.IO.MemoryStream
        $b.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        [void]$ms.Seek(0, 'Begin')
        $ras = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
        $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($ras)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
        $sb.Dispose(); $ms.Dispose()
        ($res.Lines | ForEach-Object { $_.Text }) -join ' / '
    }
    [Console]::Out.WriteLine('READY|ok'); [Console]::Out.Flush()
    while ($true) {
        $bmp = New-Object System.Drawing.Bitmap $W, $H
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size)
        $g.Dispose()
        $BW = $W * $Scale; $BH = $H * $Scale
        $big = New-Object System.Drawing.Bitmap $BW, $BH
        $g2 = [System.Drawing.Graphics]::FromImage($big)
        $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g2.DrawImage($bmp, 0, 0, $BW, $BH)
        $g2.Dispose(); $bmp.Dispose()
        $clean = New-Object System.Drawing.Bitmap $BW, $BH
        $g3 = [System.Drawing.Graphics]::FromImage($clean)
        $g3.DrawImage($big, (New-Object System.Drawing.Rectangle 0, 0, $BW, $BH), 0, 0, $BW, $BH,
                      [System.Drawing.GraphicsUnit]::Pixel, $attr)
        $g3.Dispose()
        $t1 = ReadBitmap $big
        $t2 = ReadBitmap $clean
        $big.Dispose(); $clean.Dispose()
        [Console]::Out.WriteLine('OCR|' + $t1 + ' || ' + $t2); [Console]::Out.Flush()
        Start-Sleep -Milliseconds $IntervalMs
    }
} catch {
    [Console]::Out.WriteLine('ERR|' + $_.Exception.Message); [Console]::Out.Flush()
}
"""


def available():
    return sys.platform.startswith("win")


class ScreenReader:
    def __init__(self, user_dir, on_line):
        """on_line(kind, text) is called from a background thread with
        kind = 'READY', 'OCR', 'ERR' or 'STOPPED'."""
        self.user_dir = user_dir
        self.on_line = on_line
        self.proc = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, region, interval_ms=700):
        self.stop()
        x, y, w, h = (int(v) for v in region)
        if w < 8 or h < 8:
            raise ValueError("The reading area is too small.")
        os.makedirs(self.user_dir, exist_ok=True)
        script = os.path.join(self.user_dir, "ocr_reader.ps1")
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(PS_SCRIPT)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
             "-X", str(x), "-Y", str(y), "-W", str(w), "-H", str(h), "-IntervalMs", str(interval_ms)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=flags)
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc):
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            kind, _, text = line.partition("|")
            if kind in ("READY", "OCR", "ERR"):
                self.on_line(kind, text)
            elif line.strip():
                self.on_line("ERR", line.strip())
        self.on_line("STOPPED", "")

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except OSError:
                pass
            self.proc = None
