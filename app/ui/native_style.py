"""Visual Qt compartilhado. Sem rede, recursos de IA ou estado de entidade."""
import math
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QFont, QRadialGradient, QPainterPath, QImageReader, QImage
from pathlib import Path

STYLE = """QWidget { background:#10131c; color:#e9edf5; font:13px 'Noto Sans'; }
QLabel { background:transparent; }
QLabel#brand { font-size:19px; font-weight:600; color:#f5e5ce; padding:8px; }
QLabel#subtitle { color:#929db3; padding-bottom:12px; }
QLabel#notice { background:#191f2c; color:#b6c4db; border-radius:10px; padding:10px; }
QFrame#gpuAlert { background:#3b1c25; border:1px solid #d0627a; border-radius:12px; }
QLabel#gpuAlertText { color:#ffdbe2; font-weight:600; }
QLabel#pageTitle { font-size:26px; font-weight:600; padding-top:6px; }
QScrollArea,QStackedWidget { border:0; }
QListWidget#navigation { background:#151a26; border:1px solid #252e40; border-radius:14px; padding:8px; outline:0; }
QListWidget::item { padding:12px 10px; margin:2px 0; border-radius:8px; color:#a5b1c7; }
QListWidget::item:hover { background:#202839; color:#f0f3fa; }
QListWidget::item:selected { background:#33304c; color:#ecdcff; border-left:3px solid #c6a3ed; }
QPushButton { background:#222b3d; border:1px solid #35415a; border-radius:9px; padding:9px 12px; }
QPushButton:hover { background:#303b53; border-color:#7384a8; }
QPushButton:pressed { background:#171d2c; }
QPushButton:disabled { color:#677186; background:#191f2b; border-color:#242b38; }
QPushButton[primary="true"] { background:#c8b3e8; color:#211b30; border-color:#c8b3e8; font-weight:600; }
QPushButton[primary="true"]:hover { background:#e0cef8; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#1c2332; border:1px solid #354057; border-radius:8px; padding:8px; selection-background-color:#594b76; }
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus { border-color:#b49bd7; }
QComboBox QAbstractItemView { background:#222b3d; selection-background-color:#443959; }
QPlainTextEdit,QTextBrowser,QTreeWidget { background:#151b28; border:1px solid #2c374c; border-radius:12px; padding:12px; selection-background-color:#554776; }
QTreeWidget { alternate-background-color:#1d2535; }
QTreeWidget::item { padding:5px 3px; }
QHeaderView::section { background:#20293a; padding:8px; border:0; color:#b9c6dc; }
QGroupBox { background:#191f2c; border:1px solid #303a50; border-radius:14px; margin-top:14px; padding:18px 12px 12px; }
QGroupBox::title { subcontrol-origin:margin; left:18px; padding:0 6px; color:#cdd7e8; }
QTabWidget::pane { border:1px solid #303b50; border-radius:12px; padding:10px; }
QTabBar::tab { background:#191f2c; color:#98a7c1; padding:11px 18px; margin:0 5px 5px 0; border-radius:8px; }
QTabBar::tab:selected { background:#33304c; color:#edddff; }
QCheckBox { spacing:9px; padding:5px 0; }
QCheckBox::indicator { width:15px; height:15px; border:1px solid #667592; border-radius:4px; background:#1c2332; }
QCheckBox::indicator:checked { background:#b9a0dd; border-color:#e2d1fa; }
QProgressBar { background:#1c2535; border:0; border-radius:6px; min-height:18px; text-align:center; }
QProgressBar::chunk { background:#7eaeab; border-radius:6px; }
QSlider::groove:horizontal { height:6px; background:#303b50; border-radius:3px; }
QSlider::sub-page:horizontal { background:#baa0dd; border-radius:3px; }
QSlider::handle:horizontal { background:#efdefe; width:18px; margin:-6px 0; border-radius:9px; }
QScrollBar:vertical { width:9px; background:transparent; margin:0; }
QScrollBar::handle:vertical { background:#3b4860; border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QToolTip,QMenu { background:#202839; color:#e9edf5; border:1px solid #4b5670; padding:6px; }
QMenu::item { padding:8px 14px; border-radius:5px; }
QMenu::item:selected { background:#443959; }
"""

def animation_interval(status, reduced=False, visible=True):
    if reduced or not visible:return 0
    return 66 if status in {'offline','sleeping'} else 33

def load_orb_image(path):
    """Decode bounded local raster only, never URL/SVG or huge dimensions."""
    try:
        file=Path(path)
        if not path or not file.is_absolute() or file.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'} or file.stat().st_size>10*1024**2:return QImage()
        reader=QImageReader(str(file));size=reader.size()
        if size.width()<=0 or size.height()<=0 or size.width()>4096 or size.height()>4096:return QImage()
        reader.setAutoTransform(True)
        image=reader.read()
        return image.scaled(128,128,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation) if not image.isNull() else image
    except OSError:return QImage()

def mood_color(base,mood):
    colors={'alegria':'#ffd777','feliz':'#ffd777','tristeza':'#729ddb','raiva':'#ed7888','medo':'#a79be5','amor':'#e89fbd','desejo':'#d8a1db','calma':'#90cfb9','orgulho':'#efbb73','curiosidade':'#8ed5db','vergonha':'#d49fb8','afeto':'#e6a8c4','tedio':'#91a0b3','apreensao':'#ada2d1'}
    tint=colors.get(str(mood).casefold());original=QColor(base)
    if not tint:return original.name()
    other=QColor(tint)
    return QColor(*[round(a*.65+b*.35) for a,b in zip(original.getRgb()[:3],other.getRgb()[:3])]).name()

def _corpo_numero(anim, chave, padrao, baixo, alto):
    try:
        valor=float(anim.get(chave,padrao))
    except (TypeError, ValueError):
        return padrao
    return min(alto, max(baixo, valor)) if math.isfinite(valor) else padrao

def paint_orb(painter, color, entity, status, phase=0, hover=False, identity_color=None, portrait=None, corpo=None):
    """CPU/raster only; phase is elapsed time, never inferred emotion.

    `corpo` (opcional) é a expressão do corpo pulsado, derivada só por leitura
    da emoção real: amplitude do balanço, brilho e sobressalto. Sem ele, o
    desenho é o de sempre.
    """
    painter.setRenderHint(painter.Antialiasing)
    quiet=status in {'sleeping','offline'}
    anim=(corpo or {}).get('animacao') if isinstance(corpo, dict) else None
    anim=anim if isinstance(anim, dict) else None
    amplitude=_corpo_numero(anim,'amplitude_px',1.6,0.,4.) if anim else 1.6
    salto=-4. if anim and anim.get('sobressalto') is True else 0.
    center=QPointF(44,37+math.sin(phase)*amplitude+salto)
    accent=QColor('#f3a6b0' if status=='error' else color)
    glow=QRadialGradient(center,41)
    brilho=1+(_corpo_numero(anim,'brilho',.5,.15,.85)-.5)*1.2 if anim else 1.
    a=QColor(accent);a.setAlpha(int(min(120,max(10,(35 if quiet else 65)*brilho))))
    glow.setColorAt(0,a);glow.setColorAt(.65,a);glow.setColorAt(1,QColor(0,0,0,0))
    painter.setPen(Qt.NoPen);painter.setBrush(glow);painter.drawEllipse(center,41,41)
    radius=27+(math.sin(phase*2)*1.2 if status in {'working','speaking'} else 0)
    body=QRadialGradient(center-QPointF(9,12),55)
    body.setColorAt(0,accent.lighter(125) if not quiet else accent.darker(130))
    body.setColorAt(.55,accent.darker(165));body.setColorAt(1,QColor('#172032'))
    painter.setBrush(body);painter.setPen(QPen(accent,1.4 if hover else .8));painter.drawEllipse(center,radius,radius)
    has_portrait=portrait is not None and not portrait.isNull()
    if has_portrait:
        painter.save();clip=QPainterPath();clip.addEllipse(center,radius-1,radius-1);painter.setClipPath(clip)
        side=min(portrait.width(),portrait.height());source=QRectF((portrait.width()-side)/2,(portrait.height()-side)/2,side,side)
        painter.drawImage(QRectF(center.x()-radius,center.y()-radius,radius*2,radius*2),portrait,source);painter.restore()
    identity=QColor(identity_color or color);painter.setBrush(Qt.NoBrush);painter.setPen(QPen(identity,2));painter.drawEllipse(center,radius+2,radius+2)
    painter.setBrush(Qt.NoBrush);ring=QColor(accent);ring.setAlpha(160 if hover else 75)
    painter.setPen(QPen(ring,1));rect=QRectF(center.x()-33,center.y()-33,66,66)
    angle=int(phase*22*16);painter.drawArc(rect,angle,110*16);painter.drawArc(rect,angle+180*16,45*16)
    painter.setPen(QColor('#fff4e6'));painter.setFont(QFont('Noto Sans',15,QFont.Medium))
    if not has_portrait:painter.drawText(QRectF(center.x()-20,center.y()-19,40,38),Qt.AlignCenter,entity[0].upper())
    painter.setPen(Qt.NoPen);painter.setBrush(accent if not quiet else QColor('#748097'));painter.drawEllipse(QPointF(66,58),3.5,3.5)
    painter.setPen(QColor('#eff2f9'));painter.setFont(QFont('Noto Sans',9,QFont.Medium));painter.drawText(0,78,88,20,Qt.AlignCenter,entity.capitalize())
