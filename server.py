"""PuzzleKids backend v6 - fixed semicircles, clean ghost outlines"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageChops
import base64, io, math, os, requests, time

app = Flask(__name__)
CORS(app)

def tab_dir(r, c, side):
    if side == 1:   seed = r * 9973 + c * 3119 + 7
    elif side == 2: seed = r * 9973 + c * 3119 + 17
    elif side == 0:
        seed = (r-1) * 9973 + c * 3119 + 17
        v = math.sin(seed * 127.1) * 43758.5453
        return -(1 if (v - math.floor(v)) > 0.5 else -1)
    else:
        seed = r * 9973 + (c-1) * 3119 + 7
        v = math.sin(seed * 127.1) * 43758.5453
        return -(1 if (v - math.floor(v)) > 0.5 else -1)
    v = math.sin(seed * 127.1) * 43758.5453
    return 1 if (v - math.floor(v)) > 0.5 else -1

def arc(cx, cy, radius, a0, a1, steps=32):
    return [(cx + radius*math.cos(a0 + (a1-a0)*i/steps),
             cy + radius*math.sin(a0 + (a1-a0)*i/steps))
            for i in range(steps+1)]

def make_poly(pw, ph, r, c, grid, PAD):
    ox, oy = PAD, PAD
    sw, sh = pw, ph
    rx, ry = sw * 0.22, sh * 0.22

    T = 0 if r == 0       else tab_dir(r, c, 0)
    R = 0 if c == grid-1  else tab_dir(r, c, 1)
    B = 0 if r == grid-1  else tab_dir(r, c, 2)
    L = 0 if c == 0       else tab_dir(r, c, 3)

    poly = [(ox, oy)]

    # TOP (left→right): выступ вверх = T>0, вдавлен = T<0
    if T != 0:
        poly.append((ox + sw/2 - rx, oy))
        poly += arc(ox+sw/2, oy, rx, math.pi, 0) if T > 0 else arc(ox+sw/2, oy, rx, 0, math.pi)
    poly.append((ox+sw, oy))

    # RIGHT (top→bottom): выступ вправо = R>0, вдавлен = R<0
    if R != 0:
        poly.append((ox+sw, oy+sh/2-ry))
        poly += arc(ox+sw, oy+sh/2, ry, -math.pi/2, math.pi/2) if R > 0 else arc(ox+sw, oy+sh/2, ry, math.pi/2, 3*math.pi/2)
    poly.append((ox+sw, oy+sh))

    # BOTTOM (right→left): выступ вниз = B>0, вдавлен = B<0
    if B != 0:
        poly.append((ox+sw/2+rx, oy+sh))
        poly += arc(ox+sw/2, oy+sh, rx, 0, math.pi) if B > 0 else arc(ox+sw/2, oy+sh, rx, math.pi, 0)
    poly.append((ox, oy+sh))

    # LEFT (bottom→top): выступ влево = L>0, вдавлен = L<0
    if L != 0:
        poly.append((ox, oy+sh/2+ry))
        poly += arc(ox, oy+sh/2, ry, math.pi/2, 3*math.pi/2) if L > 0 else arc(ox, oy+sh/2, ry, -math.pi/2, math.pi/2)
    poly.append((ox, oy))

    return poly

def make_mask(pw, ph, r, c, grid, PAD, SCALE=8):
    W = (pw + PAD*2) * SCALE
    H = (ph + PAD*2) * SCALE
    poly = [(x*SCALE, y*SCALE) for x,y in make_poly(pw, ph, r, c, grid, PAD)]
    mask_hi = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask_hi).polygon(poly, fill=255)
    return mask_hi.resize((pw+PAD*2, ph+PAD*2), Image.LANCZOS)

def make_board_outline(pw, ph, grid, PAD, bW, bH):
    """
    Контуры поля: пунктирные линии по форме пазла.
    Каждое ребро рисуется как один непрерывный пунктир.
    """
    result = Image.new('RGBA', (bW, bH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(result)
    COLOR = (255, 255, 255, 55)
    LW = 2
    DASH = 6
    GAP  = 4

    # Состояние пунктира — сохраняется между сегментами одного ребра
    dash_state = [True, 0.0]  # [drawing, remainder]

    def reset_dash():
        dash_state[0] = True
        dash_state[1] = 0.0

    def draw_seg(x1, y1, x2, y2):
        """Рисует отрезок с учётом текущего состояния пунктира."""
        seg_len = math.sqrt((x2-x1)**2+(y2-y1)**2)
        if seg_len < 0.001: return
        dx, dy = (x2-x1)/seg_len, (y2-y1)/seg_len
        pos = 0.0
        # Продолжаем с остатка предыдущего сегмента
        if dash_state[1] > 0:
            step = min(dash_state[1], seg_len)
            if dash_state[0]:
                draw.line([(x1, y1),(x1+dx*step, y1+dy*step)], fill=COLOR, width=LW)
            pos = step
            dash_state[1] -= step
            if dash_state[1] <= 0.001:
                dash_state[0] = not dash_state[0]
                dash_state[1] = 0.0
        while pos < seg_len - 0.001:
            budget = DASH if dash_state[0] else GAP
            step = min(budget, seg_len - pos)
            if dash_state[0]:
                draw.line([(x1+dx*pos, y1+dy*pos),(x1+dx*(pos+step), y1+dy*(pos+step))],
                          fill=COLOR, width=LW)
            pos += step
            if step >= budget - 0.001:
                dash_state[0] = not dash_state[0]
            else:
                dash_state[1] = budget - step
                break

    def dashed_line(p1, p2):
        draw_seg(p1[0], p1[1], p2[0], p2[1])

    def draw_arc_pts(cx, cy, radius, a0, a1):
        pts = arc(cx, cy, radius, a0, a1)
        for i in range(len(pts)-1):
            draw_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
        return pts[0], pts[-1]

    # Рисуем каждое уникальное ребро ровно один раз
    # Горизонтальные рёбра: между строками r и r+1, и внешние (r=0 top, r=grid-1 bottom)
    for r in range(grid + 1):
        for c in range(grid):
            ox = c * pw
            rx = pw * 0.22
            if r == 0:
                oy = 2  # отступ от края чтобы не обрезалось
                if c == 0: reset_dash()
                dashed_line((ox, oy), (ox+pw, oy))
            elif r == grid:
                oy = bH - 3
                if c == 0: reset_dash()
                dashed_line((ox, oy), (ox+pw, oy))
            else:
                oy = r * ph
                t = tab_dir(r, c, 0)
                mx = ox + pw / 2
                if c == 0: reset_dash()
                dashed_line((ox, oy), (mx - rx, oy))
                if t > 0: draw_arc_pts(mx, oy, rx, math.pi, 0)
                else:     draw_arc_pts(mx, oy, rx, 0, math.pi)
                dashed_line((mx + rx, oy), (ox + pw, oy))

    # Вертикальные рёбра: между столбцами c и c+1, и внешние
    for c in range(grid + 1):
        for r in range(grid):
            oy = r * ph
            ry = ph * 0.22
            if c == 0:
                ox = 2  # отступ от левого края
                if r == 0: reset_dash()
                dashed_line((ox, oy), (ox, oy+ph))
            elif c == grid:
                ox = bW - 3  # отступ от правого края
                if r == 0: reset_dash()
                dashed_line((ox, oy), (ox, oy+ph))
            else:
                ox = c * pw
                t = tab_dir(r, c, 3)
                my = oy + ph / 2
                if r == 0: reset_dash()
                dashed_line((ox, oy), (ox, my - ry))
                if t > 0: draw_arc_pts(ox, my, ry, math.pi/2, 3*math.pi/2)
                else:     draw_arc_pts(ox, my, ry, -math.pi/2, math.pi/2)
                dashed_line((ox, my + ry), (ox, oy + ph))

    buf = io.BytesIO()
    result.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


@app.route('/slice', methods=['POST'])
def slice_image():
    data = request.json
    img_b64 = data['image'].split(',')[-1]
    grid    = int(data.get('grid', 4))
    shape   = data.get('shape', 'square')

    img_bytes = base64.b64decode(img_b64)
    orig = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
    IW, IH = orig.size

    scale = min(1.0, 1200 / max(IW, IH))
    sw_full = int(IW * scale)
    sh_full = int(IH * scale)
    scaled = orig.resize((sw_full, sh_full), Image.LANCZOS) if scale < 1.0 else orig.copy()

    pw = sw_full // grid
    ph = sh_full // grid
    bW, bH = pw * grid, ph * grid
    if (sw_full, sh_full) != (bW, bH):
        scaled = scaled.crop((0, 0, bW, bH))

    PAD = int(max(pw, ph) * 0.26) if shape == 'jigsaw' else 0
    pieces = []
    board_outline = None
    if shape == 'jigsaw':
        board_outline = make_board_outline(pw, ph, grid, PAD, bW, bH)

    for r in range(grid):
        for c in range(grid):
            if shape == 'jigsaw':
                mask = make_mask(pw, ph, r, c, grid, PAD)

                cw, ch = pw+PAD*2, ph+PAD*2
                x0, y0 = c*pw-PAD, r*ph-PAD
                canvas = Image.new('RGBA', (cw, ch), (0,0,0,0))
                sx0, sy0 = max(0,x0), max(0,y0)
                sx1, sy1 = min(bW,x0+cw), min(bH,y0+ch)
                canvas.paste(scaled.crop((sx0,sy0,sx1,sy1)), (sx0-x0, sy0-y0))
                rc,gc,bc,ac = canvas.split()
                new_alpha = ImageChops.multiply(ac, mask)
                # Порог: пиксели с альфой < 128 → полностью прозрачные
                # Убирает полупрозрачную "каёмку" которая выглядит как линия
                import numpy as np
                alpha_arr = np.array(new_alpha)
                alpha_arr[alpha_arr < 128] = 0
                new_alpha = Image.fromarray(alpha_arr)
                result = Image.merge('RGBA',(rc,gc,bc,new_alpha))
            else:
                x0, y0 = c*pw, r*ph
                result = scaled.crop((x0,y0,x0+pw,y0+ph))

            buf = io.BytesIO()
            result.save(buf, format='PNG', optimize=False)
            pieces.append({
                'row': r, 'col': c,
                'dataURL': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(),
                'pad': PAD, 'pw': pw, 'ph': ph,
            })

    return jsonify({'pieces': pieces, 'pw': pw, 'ph': ph, 'pad': PAD,
                    'bW': bW, 'bH': bH, 'board_outline': board_outline, 'shape': shape})



import os
from flask import send_from_directory

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health_check():
    return jsonify({'status': 'ok'})

HF_TOKEN = os.environ.get('HF_TOKEN', '')

STYLE_PROMPTS = {
    'cartoon':    'vibrant cartoon illustration, Pixar-style, colorful, child-friendly, soft shading, cute characters',
    'realistic':  'photorealistic, 8k resolution, detailed textures, natural lighting, high quality photography',
    'anime':      'anime style, Studio Ghibli inspired, soft pastel colors, detailed background, beautiful illustration',
    'pixel':      'pixel art, 16-bit retro game style, clear pixels, bright colors, indie game aesthetic',
    'watercolor': 'watercolor painting, soft edges, artistic brushstrokes, delicate colors, paper texture',
    'sketch':     'pencil sketch, hand-drawn illustration, detailed linework, black and white, artistic',
}

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_text = data.get('text', '')
    style_key = data.get('style', 'cartoon')

    if not HF_TOKEN:
        return jsonify({'success': False, 'error': 'HF_TOKEN not set'}), 500

    # Translate to English via free Google Translate (no API key needed)
    src_lang = data.get('lang', 'auto')
    try:
        tr = requests.get(
            'https://translate.googleapis.com/translate_a/single',
            params={'client':'gtx','sl':src_lang,'tl':'en','dt':'t','q': user_text},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if tr.status_code == 200:
            result = tr.json()
            translated = ''.join([x[0] for x in result[0] if x[0]])
            if translated:
                user_text = translated
    except Exception:
        pass  # Use original text if translation fails

    style_prompt = STYLE_PROMPTS.get(style_key, STYLE_PROMPTS['cartoon'])
    full_prompt  = f"{style_prompt}, {user_text}, high quality, detailed"

    try:
        resp = requests.post(
            'https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell',
            headers={'Authorization': f'Bearer {HF_TOKEN}'},
            json={'inputs': full_prompt},
            timeout=60
        )

        if resp.status_code != 200:
            return jsonify({'success': False, 'error': resp.text[:200]}), 500

        # Convert image bytes to base64 dataURL
        img_b64 = base64.b64encode(resp.content).decode()
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        data_url = f'data:{content_type};base64,{img_b64}'
        return jsonify({'success': True, 'image_url': data_url})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/config')
def config():
    return jsonify({'hf_token': HF_TOKEN})


@app.route('/proxy-image')
def proxy_image():
    url = request.args.get('url', '')
    if not url:
        return 'No URL', 400
    try:
        r = requests.get(url, timeout=30)
        from flask import Response
        return Response(r.content, content_type=r.headers.get('Content-Type', 'image/webp'))
    except Exception as e:
        return str(e), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"🧩 PuzzleKids на http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
