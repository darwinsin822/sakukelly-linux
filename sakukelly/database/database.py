"""Acceso a la base de datos SQLite de la biblioteca local, streaming,
descargas, historial, estadísticas y cola de scrobbles."""
import sqlite3, os, time
from pathlib import Path
try:
    from mutagen import File as MF
except Exception:
    MF = None
from sakukelly.config import HOME, EXT

class DB:
 def __init__(self, db_path=None):
  path = Path(db_path) if db_path else (HOME/"library.db")
  self.c=sqlite3.connect(path)
  self.c.execute("""CREATE TABLE IF NOT EXISTS songs(path TEXT PRIMARY KEY,title TEXT,artist TEXT,album TEXT,genre TEXT,year TEXT,duration REAL,fav INTEGER DEFAULT 0,rating INTEGER DEFAULT 0)""")
  self.c.execute("CREATE TABLE IF NOT EXISTS folders(path TEXT PRIMARY KEY)")
  self.c.execute("CREATE TABLE IF NOT EXISTS playlists(name TEXT PRIMARY KEY)")
  self.c.execute("CREATE TABLE IF NOT EXISTS pl(name TEXT,path TEXT,pos INTEGER,PRIMARY KEY(name,path))")
  self.c.execute("CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT,played_at INTEGER,completed INTEGER DEFAULT 0)")
  self.c.execute("CREATE TABLE IF NOT EXISTS playstats(path TEXT PRIMARY KEY,plays INTEGER DEFAULT 0,skips INTEGER DEFAULT 0,last_played INTEGER DEFAULT 0,seconds INTEGER DEFAULT 0)")
  self.c.execute("CREATE TABLE IF NOT EXISTS streams(id TEXT PRIMARY KEY,title TEXT,artist TEXT,thumb TEXT,duration REAL DEFAULT 0,fav INTEGER DEFAULT 0)")
  self.c.execute("CREATE TABLE IF NOT EXISTS stream_pl(name TEXT,id TEXT,pos INTEGER,PRIMARY KEY(name,id))")
  self.c.execute("CREATE TABLE IF NOT EXISTS local_video(path TEXT PRIMARY KEY,video_id TEXT,title TEXT,artist TEXT,thumb TEXT,offset_ms INTEGER DEFAULT 0,updated_at INTEGER DEFAULT 0)")
  self.c.execute("CREATE TABLE IF NOT EXISTS downloads(id TEXT PRIMARY KEY,title TEXT,artist TEXT,path TEXT,downloaded_at INTEGER DEFAULT 0)")
  self.c.execute("CREATE TABLE IF NOT EXISTS stream_history(id INTEGER PRIMARY KEY AUTOINCREMENT,stream_id TEXT,played_at INTEGER)")
  self.c.execute("CREATE TABLE IF NOT EXISTS artist_mbid(artist TEXT PRIMARY KEY,mbid TEXT,resolved_at INTEGER DEFAULT 0)")
  self.c.execute("""CREATE TABLE IF NOT EXISTS scrobble_queue(id INTEGER PRIMARY KEY AUTOINCREMENT,service TEXT,artist TEXT,title TEXT,album TEXT,duration_s INTEGER,listened_at INTEGER,attempts INTEGER DEFAULT 0)""")
  for stmt in ("ALTER TABLE songs ADD COLUMN mbid TEXT","ALTER TABLE songs ADD COLUMN loudness_lufs REAL"):
   try:self.c.execute(stmt)
   except Exception:pass  # la columna ya existe de una ejecución anterior

  self.c.commit()
 def tag(self,a,k,d=""):
  try:return (a.get(k) or [d])[0]
  except:return d
 def scan(self,f):
  self.c.execute("INSERT OR IGNORE INTO folders VALUES(?)",(f,));n=0
  for p in Path(f).rglob("*"):
   if not p.is_file() or p.suffix.lower() not in EXT:continue
   t,ar,al,g,y,d=p.stem,"Artista desconocido","Álbum desconocido","","",0
   if MF:
    try:
     a=MF(p,easy=True)
     if a:t=self.tag(a,"title",t);ar=self.tag(a,"artist",ar);al=self.tag(a,"album",al);g=self.tag(a,"genre");y=self.tag(a,"date");d=getattr(getattr(a,"info",None),"length",0) or 0
    except:pass
   self.c.execute("""INSERT INTO songs(path,title,artist,album,genre,year,duration) VALUES(?,?,?,?,?,?,?)
   ON CONFLICT(path) DO UPDATE SET title=excluded.title,artist=excluded.artist,album=excluded.album,genre=excluded.genre,year=excluded.year,duration=excluded.duration""",(str(p),t,ar,al,g,y,d));n+=1
  self.c.commit();return n
 def remove_folder(self,f):
  f=str(Path(f))
  # Remove only the library registration. Files on disk are never deleted.
  self.c.execute("DELETE FROM folders WHERE path=?",(f,))
  prefix=f.rstrip(os.sep)+os.sep+"%"
  self.c.execute("DELETE FROM songs WHERE path LIKE ?",(prefix,))
  self.c.commit()

 def update_metadata(self,path,title=None,artist=None,album=None,year=None,genre=None,mbid=None):
  sets=[];vals=[]
  for col,val in (("title",title),("artist",artist),("album",album),("year",year),("genre",genre),("mbid",mbid)):
   if val is not None:sets.append(f"{col}=?");vals.append(val)
  if not sets:return
  vals.append(path)
  self.c.execute(f"UPDATE songs SET {','.join(sets)} WHERE path=?",vals);self.c.commit()

 def needs_metadata_cleanup(self,limit=None):
  sql="""SELECT path,title,artist,album,genre,year FROM songs
  WHERE artist='Artista desconocido' OR album='Álbum desconocido' OR year IS NULL OR year=''
  ORDER BY path"""
  if limit:sql+=f" LIMIT {int(limit)}"
  return self.c.execute(sql).fetchall()

 def songs(self,q="",fav=False):
  sql="SELECT path,title,artist,album,genre,year,duration,fav,rating FROM songs";a=[];w=[]
  if q:w.append("(title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? OR year LIKE ?)");x=f"%{q}%";a=[x]*5
  if fav:w.append("fav=1")
  if w:sql+=" WHERE "+" AND ".join(w)
  return self.c.execute(sql+" ORDER BY artist COLLATE NOCASE,album COLLATE NOCASE,title COLLATE NOCASE",a).fetchall()
 def groups(self,col):
  if col not in ("artist","album","genre","year"):
   raise ValueError("Columna no permitida")
  return self.c.execute(f"SELECT {col},COUNT(*) FROM songs WHERE {col}<>'' GROUP BY {col} ORDER BY {col} COLLATE NOCASE").fetchall()
 def fav(self,p):self.c.execute("UPDATE songs SET fav=1-fav WHERE path=?",(p,));self.c.commit()
 def is_fav(self,p):
  if not p:return False
  x=self.c.execute("SELECT fav FROM songs WHERE path=?",(p,)).fetchone()
  if x:return bool(x[0])
  x=self.c.execute("SELECT fav FROM streams WHERE id=?",(p,)).fetchone()
  if x:return bool(x[0])
  return False
 def rate(self,p,n):self.c.execute("UPDATE songs SET rating=? WHERE path=?",(n,p));self.c.commit()

 # ---- ReplayGain (loudness EBU R128 medida con ffmpeg) ----------------
 def get_loudness(self,p):
  x=self.c.execute("SELECT loudness_lufs FROM songs WHERE path=?",(p,)).fetchone()
  return x[0] if x and x[0] is not None else None
 def set_loudness(self,p,lufs):
  self.c.execute("UPDATE songs SET loudness_lufs=? WHERE path=?",(lufs,p));self.c.commit()
 def unanalyzed_paths(self,limit=None):
  sql="SELECT path FROM songs WHERE loudness_lufs IS NULL ORDER BY path"
  if limit:sql+=f" LIMIT {int(limit)}"
  return [x[0] for x in self.c.execute(sql)]
 def loudness_progress(self):
  total=self.c.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
  done=self.c.execute("SELECT COUNT(*) FROM songs WHERE loudness_lufs IS NOT NULL").fetchone()[0]
  return done,total

 # ---- MBIDs (MusicBrainz IDs), para scrobbling/similares/limpieza -----
 def get_song_mbid(self,p):
  x=self.c.execute("SELECT mbid FROM songs WHERE path=?",(p,)).fetchone()
  return x[0] if x and x[0] else None
 def set_song_mbid(self,p,mbid):
  self.c.execute("UPDATE songs SET mbid=? WHERE path=?",(mbid,p));self.c.commit()
 def get_artist_mbid(self,artist):
  x=self.c.execute("SELECT mbid FROM artist_mbid WHERE artist=?",(artist,)).fetchone()
  return x[0] if x else None  # puede ser None almacenado a propósito (ya se buscó y no hubo match)
 def artist_mbid_known(self,artist):
  x=self.c.execute("SELECT 1 FROM artist_mbid WHERE artist=?",(artist,)).fetchone()
  return x is not None
 def set_artist_mbid(self,artist,mbid):
  self.c.execute("""INSERT INTO artist_mbid(artist,mbid,resolved_at) VALUES(?,?,?)
  ON CONFLICT(artist) DO UPDATE SET mbid=excluded.mbid,resolved_at=excluded.resolved_at""",(artist,mbid,int(time.time())));self.c.commit()

 # ---- Cola de scrobbles (persistente, para no perder oyentes si falla la red) ----
 def queue_scrobble(self,service,artist,title,album,duration_s,listened_at):
  self.c.execute("INSERT INTO scrobble_queue(service,artist,title,album,duration_s,listened_at) VALUES(?,?,?,?,?,?)",
   (service,artist,title,album,duration_s,listened_at));self.c.commit()
 def pending_scrobbles(self,service,limit=25):
  return self.c.execute("SELECT id,artist,title,album,duration_s,listened_at,attempts FROM scrobble_queue WHERE service=? AND attempts<8 ORDER BY listened_at LIMIT ?",(service,limit)).fetchall()
 def drop_scrobble(self,sid):
  self.c.execute("DELETE FROM scrobble_queue WHERE id=?",(sid,));self.c.commit()
 def bump_scrobble_attempts(self,sid):
  self.c.execute("UPDATE scrobble_queue SET attempts=attempts+1 WHERE id=?",(sid,));self.c.commit()

 def pls(self):return [x[0] for x in self.c.execute("SELECT name FROM playlists ORDER BY name")]
 def newpl(self,n):self.c.execute("INSERT OR IGNORE INTO playlists VALUES(?)",(n,));self.c.commit()
 def addpl(self,n,p):
  pos=self.c.execute("SELECT COUNT(*) FROM pl WHERE name=?",(n,)).fetchone()[0];self.c.execute("INSERT OR IGNORE INTO pl VALUES(?,?,?)",(n,p,pos));self.c.commit()
 def plsongs(self,n):return self.c.execute("""SELECT s.path,s.title,s.artist,s.album,s.genre,s.year,s.duration,s.fav,s.rating FROM pl JOIN songs s ON s.path=pl.path WHERE pl.name=? ORDER BY pl.pos""",(n,)).fetchall()


 def upsert_stream(self,r):
  self.c.execute("""INSERT INTO streams(id,title,artist,thumb,duration) VALUES(?,?,?,?,?)
  ON CONFLICT(id) DO UPDATE SET title=excluded.title,artist=excluded.artist,thumb=excluded.thumb,duration=excluded.duration""",
  (r.get("id",""),r.get("title",""),r.get("artist",""),r.get("thumb",""),r.get("duration",0)));self.c.commit()
 def stream(self,i):
  x=self.c.execute("SELECT id,title,artist,thumb,duration,fav FROM streams WHERE id=?",(i,)).fetchone()
  return {"id":x[0],"title":x[1],"artist":x[2],"thumb":x[3],"duration":x[4],"fav":x[5]} if x else None
 def stream_fav(self,i):
  self.c.execute("UPDATE streams SET fav=1-fav WHERE id=?",(i,));self.c.commit()
 def stream_favs(self):
  return self.c.execute("SELECT id,title,artist,thumb,duration,fav FROM streams WHERE fav=1 ORDER BY artist COLLATE NOCASE,title COLLATE NOCASE").fetchall()
 def add_stream_pl(self,n,i):
  pos=self.c.execute("SELECT COUNT(*) FROM stream_pl WHERE name=?",(n,)).fetchone()[0]
  self.c.execute("INSERT OR IGNORE INTO stream_pl VALUES(?,?,?)",(n,i,pos));self.c.commit()
 def stream_plsongs(self,n):
  return self.c.execute("""SELECT s.id,s.title,s.artist,s.thumb,s.duration,s.fav FROM stream_pl p JOIN streams s ON s.id=p.id WHERE p.name=? ORDER BY p.pos""",(n,)).fetchall()

 def local_video(self,path):
  x=self.c.execute("SELECT video_id,title,artist,thumb,offset_ms FROM local_video WHERE path=?",(path,)).fetchone()
  return {"id":x[0],"title":x[1],"artist":x[2],"thumb":x[3],"offset_ms":x[4]} if x else None
 def set_local_video(self,path,r,offset_ms=0):
  self.c.execute("""INSERT INTO local_video(path,video_id,title,artist,thumb,offset_ms,updated_at) VALUES(?,?,?,?,?,?,?)
  ON CONFLICT(path) DO UPDATE SET video_id=excluded.video_id,title=excluded.title,artist=excluded.artist,thumb=excluded.thumb,offset_ms=excluded.offset_ms,updated_at=excluded.updated_at""",
  (path,r.get("id",""),r.get("title",""),r.get("artist",""),r.get("thumb",""),int(offset_ms),int(time.time())));self.c.commit()
 def clear_local_video(self,path):
  self.c.execute("DELETE FROM local_video WHERE path=?",(path,));self.c.commit()
 def set_local_video_offset(self,path,offset_ms):
  self.c.execute("UPDATE local_video SET offset_ms=? WHERE path=?",(int(offset_ms),path));self.c.commit()

 def recent(self,limit=80):
  return self.c.execute("""SELECT s.path,s.title,s.artist,s.album,s.genre,s.year,s.duration,s.fav,s.rating
  FROM history h JOIN songs s ON s.path=h.path GROUP BY s.path ORDER BY MAX(h.played_at) DESC LIMIT ?""",(limit,)).fetchall()
 def add_stream_history(self,i):
  self.c.execute("INSERT INTO stream_history(stream_id,played_at) VALUES(?,?)",(i,int(time.time())));self.c.commit()
 def recent_streams(self,limit=40):
  return self.c.execute("""SELECT s.id,s.title,s.artist,s.thumb,s.duration,s.fav FROM stream_history h
  JOIN streams s ON s.id=h.stream_id GROUP BY s.id ORDER BY MAX(h.played_at) DESC LIMIT ?""",(limit,)).fetchall()
 def add_download(self,i,title,artist,path):
  self.c.execute("""INSERT INTO downloads(id,title,artist,path,downloaded_at) VALUES(?,?,?,?,?)
  ON CONFLICT(id) DO UPDATE SET title=excluded.title,artist=excluded.artist,path=excluded.path,downloaded_at=excluded.downloaded_at""",
  (i,title,artist,path,int(time.time())));self.c.commit()
 def downloads(self):
  rows=self.c.execute("SELECT id,title,artist,path,downloaded_at FROM downloads ORDER BY downloaded_at DESC").fetchall()
  return [r for r in rows if Path(r[3]).exists()]
 def remove_download_record(self,i):
  self.c.execute("DELETE FROM downloads WHERE id=?",(i,));self.c.commit()

 def played(self,p):
  now=int(time.time());self.c.execute("INSERT INTO history(path,played_at) VALUES(?,?)",(p,now))
  self.c.execute("""INSERT INTO playstats(path,plays,last_played) VALUES(?,1,?)
  ON CONFLICT(path) DO UPDATE SET plays=plays+1,last_played=excluded.last_played""",(p,now));self.c.commit()
 def skip(self,p):
  self.c.execute("""INSERT INTO playstats(path,skips) VALUES(?,1)
  ON CONFLICT(path) DO UPDATE SET skips=skips+1""",(p,));self.c.commit()
 def smart(self,kind):
  rows=self.songs();st={x[0]:x[1:] for x in self.c.execute("SELECT path,plays,skips,last_played FROM playstats")}
  if kind=="Más escuchadas":return sorted(rows,key=lambda r:st.get(r[0],(0,0,0))[0],reverse=True)[:100]
  if kind=="No escuchadas recientemente":return sorted(rows,key=lambda r:st.get(r[0],(0,0,0))[2])[:100]
  if kind=="Favoritas":return [r for r in rows if r[7]]
  if kind=="Mejor valoradas":return sorted(rows,key=lambda r:r[8],reverse=True)[:100]
  return rows
 def stats(self):
  return self.c.execute("SELECT COALESCE(SUM(plays),0),COALESCE(SUM(seconds),0) FROM playstats").fetchone(),self.c.execute("SELECT path,plays FROM playstats ORDER BY plays DESC LIMIT 10").fetchall()


def folder_rows(db, folder):
    root=Path(folder)
    return [r for r in db.songs() if Path(r[0]).parent == root]


def child_folders(db, folder):
    root=Path(folder); found=set()
    for r in db.songs():
        p=Path(r[0])
        try:
            rel=p.relative_to(root)
            if len(rel.parts)>1: found.add(str(root/rel.parts[0]))
        except ValueError:
            pass
    return sorted(found,key=str.casefold)

