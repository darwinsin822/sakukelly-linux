"""Servicio MPRIS2 (control multimedia del escritorio Linux).

Se define condicionalmente: si el paquete `dbus` no está disponible en el
sistema, MPRISService queda como None y quien lo use debe comprobarlo
(igual que hacía la app monolítica original con DBUS_AVAILABLE)."""
try:
    import dbus, dbus.service
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False

from sakukelly.config import APP_NAME, MPRIS_OBJECT_PATH, MPRIS_ROOT_IFACE, MPRIS_PLAYER_IFACE

if DBUS_AVAILABLE:
    from PyQt6.QtMultimedia import QMediaPlayer

    class MPRISService(dbus.service.Object):
        """Expone Sakukelly como reproductor MPRIS2 en el bus de sesión, para
        que las teclas multimedia, el applet de sonido de Cinnamon y la
        pantalla de bloqueo puedan controlarlo, tal como esperan de
        cualquier reproductor 'serio' en Linux."""
        def __init__(self,win,bus):
            dbus.service.Object.__init__(self,bus,MPRIS_OBJECT_PATH)
            self.win=win

        # ---- org.freedesktop.DBus.Properties -----------------------------
        @dbus.service.method("org.freedesktop.DBus.Properties",in_signature="ss",out_signature="v")
        def Get(self,interface,prop):
            return self.GetAll(interface)[prop]

        @dbus.service.method("org.freedesktop.DBus.Properties",in_signature="ssv",out_signature="")
        def Set(self,interface,prop,value):
            if interface!=MPRIS_PLAYER_IFACE:return
            w=self.win
            try:
                if prop=="Volume":w.set_volume(max(0,min(100,float(value)*100)))
                elif prop=="LoopStatus":w.repeat=(str(value)=="Track")
                elif prop=="Shuffle":w.shuffle=bool(value)
            except Exception:pass

        @dbus.service.method("org.freedesktop.DBus.Properties",in_signature="s",out_signature="a{sv}")
        def GetAll(self,interface):
            w=self.win
            if interface==MPRIS_ROOT_IFACE:
                return {
                    "CanQuit":True,"CanRaise":True,"HasTrackList":False,
                    "Identity":APP_NAME,"DesktopEntry":"sakukelly",
                    "SupportedUriSchemes":dbus.Array([],signature="s"),
                    "SupportedMimeTypes":dbus.Array([],signature="s"),
                }
            if interface==MPRIS_PLAYER_IFACE:
                st=w.p.playbackState()
                status="Playing" if st==QMediaPlayer.PlaybackState.PlayingState else ("Paused" if st==QMediaPlayer.PlaybackState.PausedState else "Stopped")
                return {
                    "PlaybackStatus":status,"LoopStatus":"Track" if w.repeat else "None",
                    "Rate":1.0,"Shuffle":bool(w.shuffle),
                    "Metadata":dbus.Dictionary(w._mpris_metadata(),signature="sv"),
                    "Volume":dbus.Double(w.base_volume),"Position":dbus.Int64(w.p.position()*1000),
                    "MinimumRate":1.0,"MaximumRate":1.0,
                    "CanGoNext":True,"CanGoPrevious":True,"CanPlay":True,"CanPause":True,
                    "CanSeek":not bool(w.stream_current),"CanControl":True,
                }
            return {}

        @dbus.service.signal("org.freedesktop.DBus.Properties",signature="sa{sv}as")
        def PropertiesChanged(self,interface,changed,invalidated):
            pass

        # ---- org.mpris.MediaPlayer2 ---------------------------------------
        @dbus.service.method(MPRIS_ROOT_IFACE)
        def Raise(self):self.win.showNormal();self.win.raise_();self.win.activateWindow()
        @dbus.service.method(MPRIS_ROOT_IFACE)
        def Quit(self):self.win._really_quit=True;self.win.close()

        # ---- org.mpris.MediaPlayer2.Player --------------------------------
        @dbus.service.method(MPRIS_PLAYER_IFACE)
        def Next(self):self.win.next()
        @dbus.service.method(MPRIS_PLAYER_IFACE)
        def Previous(self):self.win.prev()
        @dbus.service.method(MPRIS_PLAYER_IFACE)
        def Pause(self):self.win.p.pause()
        @dbus.service.method(MPRIS_PLAYER_IFACE)
        def PlayPause(self):self.win.toggle()
        @dbus.service.method(MPRIS_PLAYER_IFACE)
        def Stop(self):self.win.p.stop()
        @dbus.service.method(MPRIS_PLAYER_IFACE)
        def Play(self):
            if self.win.p.playbackState()!=QMediaPlayer.PlaybackState.PlayingState:self.win.toggle()
        @dbus.service.method(MPRIS_PLAYER_IFACE,in_signature="x")
        def Seek(self,offset_us):
            if self.win.stream_current:return
            self.win.p.setPosition(max(0,self.win.p.position()+int(offset_us/1000)))
        @dbus.service.method(MPRIS_PLAYER_IFACE,in_signature="ox")
        def SetPosition(self,track_id,position_us):
            if self.win.stream_current:return
            self.win.p.setPosition(max(0,int(position_us/1000)))
        @dbus.service.method(MPRIS_PLAYER_IFACE,in_signature="s")
        def OpenUri(self,uri):pass  # no soportado
        @dbus.service.signal(MPRIS_PLAYER_IFACE,signature="x")
        def Seeked(self,position_us):pass

else:
    MPRISService = None
