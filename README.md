# Reproductor FLAC · STARTED

Reproductor de escritorio para la biblioteca local de música, con estética
retro en blanco y negro. Usa **PySide6** para la interfaz y **mpv** como motor
de audio, así que reproduce FLAC sin conversiones ni pérdida de calidad.

## Abrir

```bash
~/reproductor-flac/run.sh
```

También puedes usar el lanzador del escritorio o de `~/Descargas`.

La primera vez escanea `~/Música` o `/mnt/HDD/Musica`. Si tu música está en
otra ruta, pulsa **CARPETA**, escribe o pega la ruta y pulsa **CARGAR** (también
puedes usar **EXAMINAR…**), o ejecuta:

```bash
~/reproductor-flac/run.sh /ruta/a/tu/musica
```

## Funciones

- Escanea FLAC, MP3, OGG, OPUS, M4A, WAV, AIFF, APE y WV.
- Guarda la biblioteca en caché: al abrir, la lista aparece al instante y se
  comprueba en segundo plano si hay archivos nuevos o modificados.
- Lee título, artista, álbum, año, género, número de pista y calidad.
- Muestra la portada incrustada (con caché para cargarla al instante).
- Buscador y filtros por artista y álbum.
- Reproducción, pausa, anterior, siguiente, barra de progreso y volumen.
- Clic en cualquier punto de la barra para saltar; también se puede arrastrar.
- Modo aleatorio y repetición: desactivada, toda la lista o una pista.
- Recuerda la última pista y el segundo exacto; al abrir se retoma en pausa.
- Favoritos con corazón y vista **FAVORITOS**; se marcan con el corazón de la
  lista o con la tecla `F`.
- Listas personalizadas: crea una lista, añade canciones concretas, quita y
  reordena. También puedes usar el clic derecho sobre una pista.
- Clic derecho sobre una pista para ver toda su información: etiquetas, calidad
  y ruta del archivo.
- Temporizador de apagado: pausa la música o cierra el reproductor al terminar.
- Fondo **negro**, de **color libre** o con la **portada** de la canción actual.
- Panel del reproductor a la **izquierda o a la derecha** con el icono de intercambio.
- Iconos pixel art de 12 × 12 celdas, todos del mismo tamaño: aleatorio,
  repetir, temporizador, fondo, cambiar de lado y ocultar biblioteca.
- **Temporizador**, **Color o portada de fondo** y **ocultar biblioteca** están
  juntos en la fila superior de **AHORA SUENA**.
- Icono del ojo para **ocultar la biblioteca** y dejar solo **AHORA SUENA**.
- Cambio de carpeta escribiendo, pegando o examinando una ruta.
- Arrastra una carpeta sobre la ventana para cargarla.
- Recuerda carpeta, volumen, geometría de la ventana, fondo y modos.

## Atajos

| Tecla | Acción |
| --- | --- |
| `Espacio` | Reproducir / pausar |
| `←` / `→` | Retroceder / avanzar 5 s |
| `↑` / `↓` | Moverse por la lista |
| `Ctrl+↑` / `Ctrl+↓` | Subir / bajar volumen |
| `N` / `P` | Siguiente / anterior |
| `S` | Aleatorio |
| `R` | Cambiar repetición |
| `M` | Silenciar / recuperar volumen |
| `F` | Marcar / quitar favorito |
| Teclas multimedia | Reproducir, siguiente y anterior |
| `Ctrl+F` | Buscar |
| `Ctrl+O` | Cambiar carpeta |
| `Ctrl+L` | Cambiar el reproductor de lado |
| `Ctrl+H` | Ocultar o mostrar la biblioteca |
| `F5` | Reescanear la biblioteca |
| `Esc` | Volver a la lista |

Doble clic o `Enter` sobre una pista para reproducirla. El clic derecho abre
las opciones de favoritos, listas e información de la pista.

## Requisitos

- `python3`
- `PySide6`
- `mutagen`
- `mpv` en el `PATH`

En este equipo ya están instalados. Si faltara alguno:

```bash
sudo pacman -S mpv
pip install --user PySide6 mutagen
```

## Estructura

| Archivo | Función |
| --- | --- |
| `main.py` | Punto de entrada |
| `ui.py` | Ventana, biblioteca, listas y reproducción |
| `theme.py` | Estilos, fondo, sliders e iconos pixel art |
| `dialogs.py` | Diálogos de carpeta, fondo, listas, temporizador e información |
| `library.py` | Escaneo de etiquetas, caché de biblioteca y portadas |
| `mpv_backend.py` | Comunicación con mpv por IPC |
| `assets/fonts/` | Press Start 2P y VT323 |
| `assets/icon.svg` | Icono de la aplicación |

## Datos guardados

- Ajustes, favoritos y última sesión:
  `~/.config/STARTED/Reproductor FLAC.conf`
- Listas personalizadas: `~/.config/STARTED/playlists.json`
- Caché de la biblioteca: `~/.cache/reproductor-flac/library.json`
- Caché de portadas: `~/.cache/reproductor-flac/*.img`

Puedes borrar la caché sin miedo; se regenera al abrir la aplicación. Si borras
`playlists.json` se pierden las listas, pero no las canciones.

## Notas

- No modifica ni mueve tus archivos: solo los lee.
- Si mpv no arranca, prueba a lanzar desde una terminal para ver el error.
- En equipos sin salida de audio se puede probar con
  `REPRODUCTOR_AO=null ~/reproductor-flac/run.sh`.
