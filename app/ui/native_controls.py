"""Controles de opção sem edição pela roda; rolagem de página preservada."""
from PyQt5.QtCore import QPointF, pyqtSignal
from PyQt5.QtGui import QWheelEvent, QValidator
from PyQt5.QtWidgets import (QApplication, QAbstractScrollArea,
    QComboBox as _ComboBox, QSpinBox as _SpinBox, QDoubleSpinBox as _DoubleSpinBox,
    QSlider as _Slider, QTabBar as _TabBar, QTabWidget as _TabWidget)


class _PageWheel:
    def wheelEvent(self, event):
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                viewport = parent.viewport()
                forwarded = QWheelEvent(QPointF(viewport.mapFromGlobal(event.globalPos())),
                    event.globalPosF(), event.pixelDelta(), event.angleDelta(),
                    event.buttons(), event.modifiers(), event.phase(), event.inverted(), event.source())
                QApplication.sendEvent(viewport, forwarded)
                break
            parent = parent.parentWidget()
        # Sem propagação duplicada. Barras, listas abertas e textos não usam
        # este mixin, portanto conservam sua rolagem normal.
        event.accept()


class QComboBox(_PageWheel, _ComboBox):
    pass


class QSpinBox(_PageWheel, _SpinBox):
    pass


class QSnapSpinBox(QSpinBox):
    """06/11 (pedido humano): aceita o número digitado mesmo fora da faixa ou do passo e, ao terminar a
    edição (Enter ou sair do campo), usa o valor válido mais próximo. "24k" vale 24.576 e "24.576" também.
    Sem keyboardTracking: valueChanged só sai com o valor final, não a cada tecla (digitar 24576 passava por
    2457 e cortava o limite de saída)."""
    adjusted = pyqtSignal(int, int)  # digitado, usado

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setKeyboardTracking(False)
        self.setCorrectionMode(_SpinBox.CorrectToNearestValue)

    def nearest(self, value):
        low, high, step = self.minimum(), self.maximum(), max(1, self.singleStep())
        value = min(max(int(value), low), high)
        below = low + (value - low) // step * step
        options = [v for v in (below, below + step, high) if low <= v <= high]
        return min(options, key=lambda v: (abs(v - value), -v))

    def typed(self, text):
        text = text.strip()
        if self.prefix() and text.startswith(self.prefix()):
            text = text[len(self.prefix()):]
        if self.suffix() and text.endswith(self.suffix()):
            text = text[:-len(self.suffix())]
        text = text.strip().replace('.', '').replace(' ', '').replace('\u00a0', '').lower()
        scale = 1024 if text.endswith('k') else 1
        text = text[:-1] if scale > 1 else text
        return int(text) * scale if text.isdigit() and len(text) <= 9 else None

    def validate(self, text, pos):
        value = self.typed(text)
        if value is None:
            return (QValidator.Intermediate if not text.strip() else QValidator.Invalid), text, pos
        return (QValidator.Acceptable if self.nearest(value) == value else QValidator.Intermediate), text, pos

    def fixup(self, text):
        value = self.typed(text)
        used = self.nearest(self.value() if value is None else value)
        if value is not None and value != used:
            self.adjusted.emit(value, used)
        return self.textFromValue(used)

    def valueFromText(self, text):
        value = self.typed(text)
        return self.nearest(self.value() if value is None else value)

    def stepBy(self, steps):
        self.setValue(self.nearest(self.value() + steps * self.singleStep()))


class QDoubleSpinBox(_PageWheel, _DoubleSpinBox):
    pass


class QSlider(_PageWheel, _Slider):
    pass


class _SafeTabBar(_PageWheel, _TabBar):
    pass


class QTabWidget(_TabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(_SafeTabBar(self))
