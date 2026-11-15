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
- Muestra la letra bajo el álbum en **AHORA SUENA**, avanzando con la canción:
  lee etiquetas LRC incrustadas (`lyrics`/`unsyncedlyrics`) o archivos `.lrc`.
- Efectos al cambiar de línea de letra: **desvanecido**, **deslizar**, **máquina
  de escribir** o **sin efecto**, elegidos en **Ajustes**.
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
  y ruta del archivo, con cada etiqueta y su valor alineados por línea base.
- Temporizador de apagado: pausa la música o cierra el reproductor al terminar.
- Fondo **negro**, de **color libre**, con la **portada** de la canción actual
  o con una **imagen propia**, todo desde **Ajustes**.
- Panel del reproductor a la **izquierda o a la derecha** con el icono de intercambio.
- Botón único de **Ajustes** (engranaje) en **AHORA SUENA**: reúne el idioma,
  el fondo, el efecto de las letras y la visibilidad de la biblioteca.
- Iconos pixel art propios para aleatorio, repetir, temporizador y ajustes,
  guardados en `assets/icons/`. El de cambiar de lado sigue dibujado en la
  rejilla de 12 × 12.
- Los iconos se adaptan al fondo: **blancos** sobre fondos oscuros y **negros**
  sobre fondos claros.
- **Temporizador** y **Ajustes** están juntos en la fila superior de
  **AHORA SUENA**; desde Ajustes puedes **ocultar la biblioteca** y dejar solo
  **AHORA SUENA**. Al ocultarla, la ventana se ajusta al tamaño del panel del
  reproductor y lo recupera al volver a mostrarla, incluso si estaba maximizada.
- Cambio de carpeta escribiendo, pegando o examinando una ruta.
- Interfaz en **español**, **inglés**, **japonés** y **ruso**; el idioma se elige
  en **Ajustes** y se guarda al instante.
- Los títulos, artistas y letras en japonés usan la fuente pixel **DotGothic16**
  ajustada al mismo tamaño visual que el texto latino.
- Encabezados y celdas de las tablas comparten ancho y alineación: los textos a
  la izquierda y los números o duraciones a la derecha, con espacio entre columnas.
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
| `dialogs.py` | Diálogos de ajustes, carpeta, listas, temporizador e información |
| `library.py` | Escaneo de etiquetas, caché de biblioteca y portadas |
| `i18n.py` | Traducciones de la interfaz y selector de idioma |
| `mpv_backend.py` | Comunicación con mpv por IPC |
| `assets/fonts/` | Press Start 2P, VT323 y DotGothic16 |
| `assets/icons/` | Iconos PNG de los controles del reproductor |
| `assets/icon.svg` | Icono de la aplicación |

## Datos guardados

- Ajustes, favoritos, idioma y última sesión:
  `~/.config/STARTED/Reproductor FLAC.conf`
- La imagen de fondo se guarda como ruta en ese mismo archivo; el reproductor
  no copia ni modifica la imagen original.
- Listas personalizadas: `~/.config/STARTED/playlists.json`
- Caché de la biblioteca: `~/.cache/reproductor-flac/library.json`
- Caché de portadas: `~/.cache/reproductor-flac/*.img`

Puedes borrar la caché sin miedo; se regenera al abrir la aplicación. Si borras
`playlists.json` se pierden las listas, pero no las canciones.

## Notas

- No modifica ni mueve tus archivos: solo los lee.
- La fuente DotGothic16 se incluye con licencia SIL OFL 1.1
  (`assets/fonts/LICENSE-DotGothic16.txt`).
- Si mpv no arranca, prueba a lanzar desde una terminal para ver el error.
- En equipos sin salida de audio se puede probar con
  `REPRODUCTOR_AO=null ~/reproductor-flac/run.sh`.
