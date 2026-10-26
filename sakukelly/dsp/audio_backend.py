"""Backend DSP (ecualizador) vía PipeWire/PulseAudio + LADSPA."""
import shutil, subprocess
from pathlib import Path

class DSPBackend:
    """Ecualización DSP real mediante PipeWire/PulseAudio.
    Crea un sink virtual LADSPA y enruta Sakukelly hacia él cuando el sistema
    dispone de module-ladspa-sink y del plugin mbeq_1197.so.
    """
    def __init__(self):
        self.module_id=None
        self.sink_name="sakukelly_eq"
        self.available=False
        self.pactl=shutil.which("pactl")
        self.plugin=self._find_plugin()
        self.available=bool(self.pactl and self.plugin)

    def _find_plugin(self):
        candidates=[
            "/usr/lib/ladspa/mbeq_1197.so",
            "/usr/lib/x86_64-linux-gnu/ladspa/mbeq_1197.so",
            "/usr/lib/aarch64-linux-gnu/ladspa/mbeq_1197.so",
        ]
        return next((x for x in candidates if Path(x).exists()), None)

    def _run(self,*args):
        try:
            return subprocess.run([self.pactl,*args],capture_output=True,text=True,timeout=4)
        except Exception:
            return None

    def unload(self):
        if self.module_id:
            self._run("unload-module",str(self.module_id))
            self.module_id=None

    def apply(self, bands):
        if not self.available:
            return False, "DSP no disponible"
        self.unload()
        # mbeq usa 15 bandas. Interpolamos las 8 del mockup a sus centros.
        src=[60,150,400,1000,2400,6000,12000,16000]
        dst=[50,100,156,220,311,440,622,880,1250,1750,2500,3500,5000,10000,20000]
        def interp(x):
            if x<=src[0]: return bands[0]
            if x>=src[-1]: return bands[-1]
            for i in range(len(src)-1):
                if src[i]<=x<=src[i+1]:
                    a=(x-src[i])/(src[i+1]-src[i])
                    return bands[i]*(1-a)+bands[i+1]*a
            return 0
        # LADSPA mbeq recibe ganancias lineales aproximadas por banda.
        vals=[10**(interp(x)/20.0) for x in dst]
        control=",".join(f"{v:.4f}" for v in vals)
        default_sink=self._run("get-default-sink")
        master=default_sink.stdout.strip() if default_sink and default_sink.returncode==0 else ""
        args=["load-module","module-ladspa-sink",
              f"sink_name={self.sink_name}",
              f"plugin={Path(self.plugin).stem}",
              "label=mbeq",
              f"control={control}"]
        if master: args.append(f"master={master}")
        r=self._run(*args)
        if not r or r.returncode!=0:
            return False, (r.stderr.strip() if r else "No se pudo cargar LADSPA")
        self.module_id=r.stdout.strip()
        return True, self.sink_name

