"""
Generates dark_mode.svg and light_mode.svg from profile.json (+ an optional portrait image).

    python make_svg.py                      # uses profile.json, portrait.png if present
    python make_svg.py --image me.jpg       # choose the portrait explicitly

The SVG keeps the element ids that today.py rewrites daily (age_data, repo_data, ...),
so after generating, the GitHub Action fills in your live stats.
"""
import argparse, json, os, sys
from xml.sax.saxutils import escape

ART_FONT = 10                         # px; a small font = more characters = more facial detail
ASCII_COLS, ASCII_ROWS = 60, 46      # portrait size in characters
CELL_W = 6.0                          # approx px width of one portrait character
ART_LINE = 10                         # px between portrait lines
LINE_H = 20                           # px between lines
TEXT_X = 390                          # where the info column starts
WIDTH_CHARS = 58                      # width of the info column in characters
IDE_FALLBACK = 'VSCode, PyCharm, IntelliJ IDEA'   # shown until the first Action run fills in versions
RAMP = " .,:;ilt1fLCG08@"             # light -> dark

THEMES = {
    'dark':  dict(bg='#161b22', fg='#c9d1d9', key='#ffa657', value='#a5d6ff', add='#3fb950', dele='#f85149', cc='#616e7f', invert=False),
    'light': dict(bg='#f6f8fa', fg='#24292f', key='#953800', value='#0a3069', add='#1a7f37', dele='#cf222e', cc='#c2cfde', invert=True),
}

def find_face(im):
    """Returns (cx, cy, size) of the face in pixels. Uses OpenCV's face detector if installed,
    otherwise falls back to the centre of the upper part of the cut-out subject."""
    from PIL import Image
    alpha = im.getchannel('A').point(lambda v: 255 if v > 128 else 0)
    bbox = alpha.getbbox() or (0, 0, im.width, im.height)
    try:
        import cv2, numpy as np
        rgb = Image.new('RGB', im.size, (127, 127, 127)); rgb.paste(im, mask=im.getchannel('A'))
        g = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = [] if det.empty() else det.detectMultiScale(g, 1.1, 5, minSize=(im.width // 8, im.width // 8))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            return x + w / 2, y + h / 2, h
    except ImportError:
        pass
    import numpy as np
    top = np.array(alpha.crop((0, bbox[1], im.width, bbox[1] + (bbox[3] - bbox[1]) // 2)))
    xs = np.nonzero(top.sum(axis=0))[0]
    cx = (xs.min() + xs.max()) / 2 if len(xs) else im.width / 2
    head_h = (bbox[3] - bbox[1]) * 0.55
    return cx, bbox[1] + head_h * 0.55, head_h * 0.6


def image_to_ascii(path, invert, zoom=1.0):
    """RGBA/RGB image -> list of text rows. Transparent pixels become blank space.
    The window is centred on the detected face."""
    from PIL import Image, ImageOps, ImageFilter
    im = Image.open(path).convert('RGBA')
    fx, fy, fh = find_face(im)
    size = (int(ASCII_COLS * CELL_W * 10), ASCII_ROWS * ART_LINE * 10)       # same aspect as the text block
    ch = fh * 3.0 / zoom                                                      # window height: ~3 face-heights (hair to chest)
    cw = ch * size[0] / size[1]
    left, top = fx - cw / 2, fy - ch * 0.42                                   # face sits just above the vertical middle
    canvas = Image.new('RGBA', (int(cw), int(ch)), (0, 0, 0, 0))              # transparent padding if the window leaves the photo
    canvas.paste(im, (int(-left), int(-top)))
    im = canvas.resize(size, Image.LANCZOS)
    alpha = im.getchannel('A')
    gray = im.convert('L').filter(ImageFilter.UnsharpMask(radius=6, percent=180, threshold=2))   # crisper eyes, brows, mouth
    gray = ImageOps.autocontrast(gray, cutoff=0.5, mask=alpha.point(lambda v: 255 if v > 128 else 0))
    g = 1.7 if invert else 0.95                                           # light theme: darker mid-tones so the face has structure on a pale background
    gray = gray.point(lambda v: int(255 * (v / 255) ** g))
    bg = Image.new('L', size, 255 if invert else 0)
    bg.paste(gray, mask=alpha)                                                # background -> blank
    bg = bg.resize((ASCII_COLS, ASCII_ROWS), Image.LANCZOS)
    ramp = RAMP[::-1] if invert else RAMP
    return [''.join(ramp[min(len(ramp) - 1, bg.getpixel((x, y)) * len(ramp) // 256)] for x in range(ASCII_COLS))
            for y in range(ASCII_ROWS)]

AGE_TEXT = '0 years, 0 months, 0 days'

def age_text(birthday):
    """'21 years, 10 months, 12 days' - same wording today.py produces"""
    import datetime
    from dateutil import relativedelta
    d = relativedelta.relativedelta(datetime.datetime.today(), datetime.datetime.strptime(birthday, '%Y-%m-%d'))
    pl = lambda n: '' if n == 1 else 's'
    return f'{d.years} year{pl(d.years)}, {d.months} month{pl(d.months)}, {d.days} day{pl(d.days)}'

def dots(label_len, value_len):
    n = max(2, WIDTH_CHARS - 2 - label_len - 1 - value_len)
    return ' ' + '.' * n + ' '

def field(y, label, value, ids=None):
    """One 'key: ..... value' line. label may be dotted, e.g. Languages.Real"""
    parts = label.split('.')
    key_html = '<tspan class="cc">. </tspan>' + '.'.join(f'<tspan class="key">{escape(p)}</tspan>' for p in parts)
    if value == '__IDE__':                      # kept current by today.py (latest VS Code / JetBrains versions)
        txt = escape(IDE_FALLBACK)
        val = '<tspan class="cc" id="ide_data_dots">%s</tspan><tspan class="value" id="ide_data">%s</tspan>' % (dots(len(label), len(IDE_FALLBACK)), txt)
    elif value == '__AGE__':                    # today.py re-justifies this daily; the text here is already exact
        d = dots(len(label), len(AGE_TEXT))
        val = '<tspan class="cc" id="age_data_dots">%s</tspan><tspan class="value" id="age_data">%s</tspan>' % (d, AGE_TEXT)
    else:
        d = dots(len(label), len(value))
        val = f'<tspan class="cc">{d}</tspan><tspan class="value">{escape(value)}</tspan>'
    return f'<tspan x="{TEXT_X}" y="{y}">{key_html}:{val}</tspan>'

def header(y, text):
    pad = max(2, WIDTH_CHARS - len(text) - 3)
    return f'<tspan x="{TEXT_X}" y="{y}">{escape(text)}</tspan> -{"—" * pad}-—-'

def build(theme, cfg, ascii_rows):
    t = THEMES[theme]
    lines, y = [], 30
    lines.append(header(y, cfg['title']).replace(' -', ' -', 1)); y += 20
    for item in cfg['info']:
        lines.append(f'<tspan x="{TEXT_X}" y="{y}" class="cc">. </tspan>' if item is None else field(y, *item))
        y += 20
    y += 20
    lines.append(header(y, '- Contact')); y += 20
    for label, value in cfg['contact']:
        lines.append(field(y, label, value)); y += 20
    y += 20
    lines.append(header(y, '- GitHub Stats')); y += 20
    stats = [
        f'<tspan x="{TEXT_X}" y="{y}" class="cc">. </tspan><tspan class="key">Repos</tspan>:<tspan class="cc" id="repo_data_dots"> .... </tspan><tspan class="value" id="repo_data">0</tspan> {{<tspan class="key">Contributed</tspan>: <tspan class="value" id="contrib_data">0</tspan>}} | <tspan class="key">Stars</tspan>:<tspan class="cc" id="star_data_dots"> ........... </tspan><tspan class="value" id="star_data">0</tspan>',
        f'<tspan x="{TEXT_X}" y="{y+20}" class="cc">. </tspan><tspan class="key">Commits</tspan>:<tspan class="cc" id="commit_data_dots"> ................. </tspan><tspan class="value" id="commit_data">0</tspan> | <tspan class="key">Followers</tspan>:<tspan class="cc" id="follower_data_dots"> ....... </tspan><tspan class="value" id="follower_data">0</tspan>',
        f'<tspan x="{TEXT_X}" y="{y+40}" class="cc">. </tspan><tspan class="key">Lines of Code on GitHub</tspan>:<tspan class="cc" id="loc_data_dots">. </tspan><tspan class="value" id="loc_data">0</tspan> ( <tspan class="addColor" id="loc_add">0</tspan><tspan class="addColor">++</tspan>, <tspan id="loc_del_dots"> </tspan><tspan class="delColor" id="loc_del">0</tspan><tspan class="delColor">--</tspan> )',
    ]
    lines += stats
    height = y + 40 + 20

    art = '\n'.join(f'<tspan x="15" y="{30 + i*ART_LINE}">{escape(r)}</tspan>' for i, r in enumerate(ascii_rows)) if ascii_rows else ''
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="985px" height="{max(height, 30 + ASCII_ROWS*ART_LINE + 10)}px" font-size="16px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{fill: {t['key']};}}
.value {{fill: {t['value']};}}
.addColor {{fill: {t['add']};}}
.delColor {{fill: {t['dele']};}}
.cc {{fill: {t['cc']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="985px" height="{max(height, 30 + ASCII_ROWS*ART_LINE + 10)}px" fill="{t['bg']}" rx="15"/>
<text x="15" y="30" fill="{t['fg']}" class="ascii" font-size="{ART_FONT}px">
{art}
</text>
<text x="{TEXT_X}" y="30" fill="{t['fg']}">
{chr(10).join(lines)}
</text>
</svg>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='profile.json')
    ap.add_argument('--image', default='portrait.png')
    ap.add_argument('--zoom', type=float, default=1.15, help='>1 crops tighter around the face')
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    global AGE_TEXT
    if cfg.get('birthday'):
        try: AGE_TEXT = age_text(cfg['birthday'])
        except ImportError: pass   # python-dateutil missing: keep the placeholder, today.py fixes it on the first run
    have_img = os.path.exists(a.image)
    if not have_img:
        print(f'note: {a.image} not found, generating without a portrait', file=sys.stderr)
    for theme in THEMES:
        rows = image_to_ascii(a.image, THEMES[theme]['invert'], a.zoom) if have_img else None   # light theme gets its own, tone-inverted portrait (dark features = dense characters)
        open(f'{theme}_mode.svg', 'w', encoding='utf-8').write(build(theme, cfg, rows))
        print(f'wrote {theme}_mode.svg')

if __name__ == '__main__':
    main()
