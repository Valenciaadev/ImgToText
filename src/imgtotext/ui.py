from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from imgtotext.credentials import CredentialStore
from imgtotext.exporters import ExportError, export_docx, export_json, export_pdf
from imgtotext.gemini_service import GeminiService, GeminiServiceError
from imgtotext.importer import ImageImporter
from imgtotext.models import (
    DescriptionLength,
    DescriptionMode,
    DescriptionResult,
    GenerationOptions,
    ImageItem,
    ImageStatus,
)


MODE_LABELS = {
    "Descripcion general": DescriptionMode.GENERAL,
    "Texto alternativo accesible": DescriptionMode.ACCESSIBILITY,
    "Catalogo e inventario": DescriptionMode.CATALOG,
    "Texto visible (OCR)": DescriptionMode.VISIBLE_TEXT,
}

LENGTH_LABELS = {
    "Breve": DescriptionLength.SHORT,
    "Media": DescriptionLength.MEDIUM,
    "Detallada": DescriptionLength.LONG,
}

STATUS_LABELS = {
    ImageStatus.PENDING: "Pendiente",
    ImageStatus.PROCESSING: "Analizando...",
    ImageStatus.COMPLETED: "Completada",
    ImageStatus.ERROR: "Error",
    ImageStatus.CANCELLED: "Cancelada",
}


class WorkerSignals(QObject):
    success = Signal(str, object)
    error = Signal(str, str)
    cancelled = Signal(str)
    finished = Signal(str)
    progress = Signal(str, int, str)


class GenerationWorker(QRunnable):
    def __init__(
        self,
        item: ImageItem,
        api_key: str,
        options: GenerationOptions,
        cancel_event: threading.Event,
        regeneration_note: str = "",
    ) -> None:
        super().__init__()
        self.item = item
        self.api_key = api_key
        self.options = options
        self.cancel_event = cancel_event
        self.regeneration_note = regeneration_note
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.cancel_event.is_set():
                self.signals.cancelled.emit(self.item.id)
                return
            self.signals.progress.emit(self.item.id, 3, "Iniciando el procesamiento")
            service = GeminiService(self.api_key)
            result = service.describe(
                self.item.path,
                self.options,
                self.regeneration_note,
                progress_callback=lambda value, message: self.signals.progress.emit(
                    self.item.id, value, message
                ),
            )
            if self.cancel_event.is_set():
                self.signals.cancelled.emit(self.item.id)
            else:
                self.signals.success.emit(self.item.id, result)
        except GeminiServiceError as exc:
            self.signals.error.emit(self.item.id, str(exc))
        except Exception as exc:
            self.signals.error.emit(self.item.id, f"Error inesperado: {exc}")
        finally:
            self.signals.finished.emit(self.item.id)


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        title = QLabel("Arrastra aqui imagenes o un archivo ZIP")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("PNG, JPG, JPEG o WebP · hasta 500 imagenes")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class ImageCard(QFrame):
    regenerate_requested = Signal(str)
    remove_requested = Signal(str)
    description_changed = Signal(str, str)

    def __init__(self, item: ImageItem) -> None:
        super().__init__()
        self.item_id = item.id
        self._batch_busy = False
        self.setObjectName("imageCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self.preview = QLabel()
        self.preview.setObjectName("preview")
        self.preview.setFixedSize(184, 124)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setPixmap(self._load_preview(item.path))
        root.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

        content = QVBoxLayout()
        header = QHBoxLayout()
        self.name_label = QLabel(item.display_name)
        self.name_label.setObjectName("cardTitle")
        self.name_label.setToolTip(item.display_name)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusPending")
        header.addWidget(self.name_label)
        header.addWidget(self.status_label)
        content.addLayout(header)

        self.meta_label = QLabel(f"{item.width} × {item.height} px")
        self.meta_label.setObjectName("cardMeta")
        content.addWidget(self.meta_label)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("La descripcion aparecera aqui...")
        self.description_edit.setMinimumHeight(92)
        self.description_edit.textChanged.connect(self._description_edited)
        content.addWidget(self.description_edit)

        self.detail_label = QLabel()
        self.detail_label.setObjectName("detailLabel")
        self.detail_label.setWordWrap(True)
        self.detail_label.hide()
        content.addWidget(self.detail_label)
        root.addLayout(content, 1)

        actions = QVBoxLayout()
        self.copy_button = QPushButton("Copiar")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy)
        self.regenerate_button = QPushButton("Regenerar")
        self.regenerate_button.setEnabled(False)
        self.regenerate_button.clicked.connect(lambda: self.regenerate_requested.emit(self.item_id))
        self.remove_button = QPushButton("Quitar")
        self.remove_button.setObjectName("quietButton")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.item_id))
        actions.addWidget(self.copy_button)
        actions.addWidget(self.regenerate_button)
        actions.addStretch()
        actions.addWidget(self.remove_button)
        root.addLayout(actions)
        self.update_item(item)

    def update_item(self, item: ImageItem) -> None:
        self.status_label.setText(STATUS_LABELS[item.status])
        self.status_label.setProperty("status", item.status.value)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if self.description_edit.toPlainText() != item.description:
            self.description_edit.blockSignals(True)
            self.description_edit.setPlainText(item.description)
            self.description_edit.blockSignals(False)
        details: list[str] = []
        if item.visible_text:
            details.append(f"Texto visible: {item.visible_text}")
        if item.uncertainty:
            details.append(f"Observacion: {item.uncertainty}")
        if item.error:
            details.append(item.error)
        self.detail_label.setText("\n".join(details))
        self.detail_label.setVisible(bool(details))
        has_text = bool(item.description.strip())
        busy = item.status == ImageStatus.PROCESSING
        self.copy_button.setEnabled(has_text)
        self.regenerate_button.setEnabled(has_text and not busy and not self._batch_busy)
        self.remove_button.setEnabled(not busy and not self._batch_busy)
        self.description_edit.setReadOnly(busy)

    def set_batch_busy(self, busy: bool) -> None:
        self._batch_busy = busy
        self.regenerate_button.setEnabled(
            bool(self.description_edit.toPlainText().strip()) and not busy
        )
        self.remove_button.setEnabled(not busy)

    def _load_preview(self, path: Path) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            size.scale(QSize(360, 240), Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image).scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.description_edit.toPlainText().strip())
        self.copy_button.setText("Copiado")

    def _description_edited(self) -> None:
        self.copy_button.setText("Copiar")
        self.description_changed.emit(self.item_id, self.description_edit.toPlainText())


class SettingsDialog(QDialog):
    def __init__(self, credentials: CredentialStore, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.credentials = credentials
        self.settings = settings
        self.setWindowTitle("Configuracion")
        self.setMinimumWidth(470)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Clave configurada" if credentials.get() else "Pega tu clave de Gemini")
        self.model_edit = QLineEdit(settings.value("model", "gemini-3.6-flash"))
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 4)
        self.concurrent_spin.setValue(int(settings.value("concurrency", 3)))
        self.persist_check = QCheckBox("Guardar en Windows Credential Manager")
        self.persist_check.setChecked(True)
        form.addRow("Clave de Gemini", self.key_edit)
        form.addRow("Modelo", self.model_edit)
        form.addRow("Procesos simultaneos", self.concurrent_spin)
        root.addLayout(form)
        root.addWidget(self.persist_check)
        note = QLabel("La clave no se escribe en los archivos del proyecto. Las variables GOOGLE_API_KEY y GEMINI_API_KEY tienen prioridad.")
        note.setObjectName("dialogNote")
        note.setWordWrap(True)
        root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept(self) -> None:
        model = self.model_edit.text().strip()
        if not model:
            QMessageBox.warning(self, "Configuracion", "Indica un modelo de Gemini")
            return
        key = self.key_edit.text().strip()
        if key:
            try:
                self.credentials.save(key, self.persist_check.isChecked())
            except RuntimeError as exc:
                QMessageBox.warning(self, "Clave", str(exc) + ". Se usara solo durante esta sesion.")
                self.credentials.save(key, False)
        self.settings.setValue("model", model)
        self.settings.setValue("concurrency", self.concurrent_spin.value())
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ImgToText")
        self.resize(1180, 780)
        self.setMinimumSize(920, 620)
        self.settings = QSettings("ImgToText", "ImgToText")
        self.credentials = CredentialStore()
        self.importer = ImageImporter()
        self.items: list[ImageItem] = []
        self.cards: dict[str, ImageCard] = {}
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(int(self.settings.value("concurrency", 3)))
        self.cancel_event = threading.Event()
        self.active_jobs = 0
        self.batch_total = 0
        self.batch_finished = 0
        self.job_progress: dict[str, int] = {}
        self.job_stages: dict[str, str] = {}
        self.progress_hold = False
        self.progress_pulse = QTimer(self)
        self.progress_pulse.setInterval(700)
        self.progress_pulse.timeout.connect(self._pulse_progress)
        self.progress_completion_timer = QTimer(self)
        self.progress_completion_timer.setSingleShot(True)
        self.progress_completion_timer.setInterval(2800)
        self.progress_completion_timer.timeout.connect(self._hide_finished_progress)
        self._build_ui()
        self._refresh_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel("ImgToText")
        title.setObjectName("appTitle")
        subtitle = QLabel("Descripciones visuales precisas, una imagen a la vez")
        subtitle.setObjectName("appSubtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        header.addLayout(title_column)
        header.addStretch()
        self.settings_button = QPushButton("Configuracion")
        self.settings_button.setObjectName("quietButton")
        self.settings_button.clicked.connect(self._open_settings)
        header.addWidget(self.settings_button)
        root.addLayout(header)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._import_paths)
        root.addWidget(self.drop_zone)

        import_row = QHBoxLayout()
        self.add_images_button = QPushButton("Agregar imagenes")
        self.add_images_button.clicked.connect(self._choose_images)
        self.add_zip_button = QPushButton("Agregar ZIP")
        self.add_zip_button.setObjectName("secondaryButton")
        self.add_zip_button.clicked.connect(self._choose_zip)
        import_row.addWidget(self.add_images_button)
        import_row.addWidget(self.add_zip_button)
        import_row.addStretch()
        self.count_label = QLabel("0 imagenes")
        self.count_label.setObjectName("countLabel")
        import_row.addWidget(self.count_label)
        root.addLayout(import_row)

        controls = QFrame()
        controls.setObjectName("controls")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.addWidget(QLabel("Modo"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODE_LABELS.keys())
        controls_layout.addWidget(self.mode_combo)
        controls_layout.addWidget(QLabel("Longitud"))
        self.length_combo = QComboBox()
        self.length_combo.addItems(LENGTH_LABELS.keys())
        self.length_combo.setCurrentText("Media")
        controls_layout.addWidget(self.length_combo)
        controls_layout.addWidget(QLabel("Contexto"))
        self.context_edit = QLineEdit()
        self.context_edit.setPlaceholderText("Opcional: fotos de inventario, evento, propiedad...")
        controls_layout.addWidget(self.context_edit, 1)
        root.addWidget(controls)

        self.empty_label = QLabel("Todavia no hay imagenes\nAgrega archivos para comenzar")
        self.empty_label.setObjectName("emptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label, 1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_content = QWidget()
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        progress_area = QVBoxLayout()
        progress_area.setSpacing(4)
        self.progress_label = QLabel("Preparando...")
        self.progress_label.setObjectName("progressLabel")
        self.progress_label.hide()
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setMinimumWidth(260)
        self.progress.hide()
        progress_area.addWidget(self.progress_label)
        progress_area.addWidget(self.progress)
        footer.addLayout(progress_area)
        footer.addStretch()
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel)
        self.export_button = QToolButton()
        self.export_button.setText("Exportar")
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_menu = QMenu(self.export_button)
        for label, kind in (("Documento PDF", "pdf"), ("Documento Word", "docx"), ("Datos JSON", "json")):
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, export_kind=kind: self._export(export_kind))
            export_menu.addAction(action)
        self.export_button.setMenu(export_menu)
        self.generate_button = QPushButton("Generar descripciones")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self._generate_pending)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.export_button)
        footer.addWidget(self.generate_button)
        root.addLayout(footer)

    def _choose_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar imagenes",
            "",
            "Imagenes (*.png *.jpg *.jpeg *.webp)",
        )
        if paths:
            self._import_paths(paths)

    def _choose_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar ZIP", "", "Archivos ZIP (*.zip)")
        if path:
            self._import_paths([path])

    @Slot(list)
    def _import_paths(self, paths: list[str]) -> None:
        new_items, errors = self.importer.load_paths(paths)
        for item in new_items:
            self.items.append(item)
            card = ImageCard(item)
            card.regenerate_requested.connect(self._regenerate)
            card.remove_requested.connect(self._remove_item)
            card.description_changed.connect(self._update_description)
            self.cards[item.id] = card
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._refresh_ui()
        if errors:
            shown = "\n".join(errors[:12])
            if len(errors) > 12:
                shown += f"\n... y {len(errors) - 12} avisos mas"
            QMessageBox.warning(self, "Algunos archivos no se agregaron", shown)

    def _generation_options(self) -> GenerationOptions:
        return GenerationOptions(
            mode=MODE_LABELS[self.mode_combo.currentText()],
            length=LENGTH_LABELS[self.length_combo.currentText()],
            language="Espanol",
            context=self.context_edit.text().strip(),
            model=str(self.settings.value("model", "gemini-3.6-flash")),
            thinking_level="low",
        )

    def _generate_pending(self) -> None:
        candidates = [item for item in self.items if item.status in {ImageStatus.PENDING, ImageStatus.ERROR, ImageStatus.CANCELLED}]
        if not candidates:
            QMessageBox.information(self, "ImgToText", "No hay imagenes pendientes")
            return
        if not self._ensure_api_key():
            return
        self.cancel_event.clear()
        self.batch_total = len(candidates)
        self.batch_finished = 0
        self.job_progress = {item.id: 0 for item in candidates}
        self.job_stages = {item.id: "En cola" for item in candidates}
        self.progress_hold = False
        self.progress_completion_timer.stop()
        self.progress_pulse.start()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label.setText(f"Preparando {self.batch_total} imagen{'es' if self.batch_total != 1 else ''}...")
        for item in candidates:
            self._start_worker(item)
        self._refresh_ui()

    def _start_worker(self, item: ImageItem, regeneration_note: str = "") -> None:
        item.status = ImageStatus.PROCESSING
        item.error = ""
        self.cards[item.id].update_item(item)
        self.active_jobs += 1
        worker = GenerationWorker(
            item=item,
            api_key=self.credentials.get(),
            options=self._generation_options(),
            cancel_event=self.cancel_event,
            regeneration_note=regeneration_note,
        )
        worker.signals.success.connect(self._worker_success)
        worker.signals.error.connect(self._worker_error)
        worker.signals.cancelled.connect(self._worker_cancelled)
        worker.signals.finished.connect(self._worker_finished)
        worker.signals.progress.connect(self._worker_progress)
        self.thread_pool.start(worker)

    @Slot(str, int, str)
    def _worker_progress(self, item_id: str, value: int, message: str) -> None:
        if item_id not in self.job_progress:
            return
        self.job_progress[item_id] = max(self.job_progress[item_id], min(value, 100))
        self.job_stages[item_id] = message
        self._update_aggregate_progress(message)

    @Slot(str, object)
    def _worker_success(self, item_id: str, result: DescriptionResult) -> None:
        item = self._item(item_id)
        if not item:
            return
        item.status = ImageStatus.COMPLETED
        item.description = result.description
        item.visible_text = result.visible_text
        item.uncertainty = result.uncertainty
        item.error = ""
        self.cards[item_id].update_item(item)

    @Slot(str, str)
    def _worker_error(self, item_id: str, message: str) -> None:
        item = self._item(item_id)
        if not item:
            return
        item.status = ImageStatus.ERROR
        item.error = message
        self.cards[item_id].update_item(item)

    @Slot(str)
    def _worker_cancelled(self, item_id: str) -> None:
        item = self._item(item_id)
        if not item:
            return
        item.status = ImageStatus.CANCELLED
        item.error = "Procesamiento cancelado"
        self.cards[item_id].update_item(item)

    @Slot(str)
    def _worker_finished(self, item_id: str) -> None:
        if item_id in self.job_progress:
            self.job_progress[item_id] = 100
        self.active_jobs = max(0, self.active_jobs - 1)
        self.batch_finished = min(self.batch_total, self.batch_finished + 1)
        self._update_aggregate_progress(self.job_stages.get(item_id, "Finalizando"))
        if self.active_jobs == 0:
            self.progress_pulse.stop()
            self.progress.setValue(100)
            cancelled = sum(item.status == ImageStatus.CANCELLED for item in self.items)
            errors = sum(item.status == ImageStatus.ERROR for item in self.items)
            if cancelled:
                self.progress_label.setText("Procesamiento cancelado")
            elif errors:
                self.progress_label.setText("Proceso terminado con algunos errores")
            else:
                self.progress_label.setText("Proceso completado")
            self.progress_hold = True
            self.progress_completion_timer.start()
        self._refresh_ui()

    @Slot(str)
    def _regenerate(self, item_id: str) -> None:
        if self.active_jobs:
            QMessageBox.information(self, "ImgToText", "Espera a que termine el lote actual o cancelalo")
            return
        if not self._ensure_api_key():
            return
        note, accepted = QInputDialog.getText(
            self,
            "Regenerar descripcion",
            (
                "Se usaran el modo, la longitud y el contexto seleccionados actualmente.\n"
                "Indicacion adicional (opcional):"
            ),
            text="Describe la imagen de otra manera sin inventar detalles.",
        )
        if not accepted:
            return
        item = self._item(item_id)
        if not item:
            return
        self.cancel_event.clear()
        self.batch_total = 1
        self.batch_finished = 0
        self.job_progress = {item.id: 0}
        self.job_stages = {item.id: "En cola"}
        self.progress_hold = False
        self.progress_completion_timer.stop()
        self.progress_pulse.start()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label.setText("Preparando la regeneracion...")
        self._start_worker(item, note)
        self._refresh_ui()

    @Slot(str)
    def _remove_item(self, item_id: str) -> None:
        item = self._item(item_id)
        card = self.cards.pop(item_id, None)
        if not item or not card:
            return
        self.items.remove(item)
        self.importer.forget(item)
        self.cards_layout.removeWidget(card)
        card.deleteLater()
        self._refresh_ui()

    @Slot(str, str)
    def _update_description(self, item_id: str, text: str) -> None:
        item = self._item(item_id)
        if item:
            item.description = text

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("Cancelando tareas pendientes...")

    def _pulse_progress(self) -> None:
        changed = False
        for item_id, value in tuple(self.job_progress.items()):
            item = self._item(item_id)
            if item and item.status == ImageStatus.PROCESSING and 42 <= value < 84:
                self.job_progress[item_id] = value + 1
                changed = True
        if changed:
            self._update_aggregate_progress("Gemini esta analizando el contenido visual")

    def _update_aggregate_progress(self, latest_stage: str) -> None:
        if not self.job_progress:
            return
        estimated = round(sum(self.job_progress.values()) / len(self.job_progress))
        self.progress.setValue(max(0, min(estimated, 100)))
        finished = sum(value >= 100 for value in self.job_progress.values())
        prefix = f"{finished}/{self.batch_total} completadas" if self.batch_total > 1 else "Procesando imagen"
        self.progress_label.setText(f"{prefix} · {latest_stage}")

    def _hide_finished_progress(self) -> None:
        self.progress_hold = False
        self.progress.hide()
        self.progress_label.hide()

    def _open_settings(self) -> bool:
        dialog = SettingsDialog(self.credentials, self.settings, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self.thread_pool.setMaxThreadCount(int(self.settings.value("concurrency", 3)))
        return accepted

    def _ensure_api_key(self) -> bool:
        if self.credentials.get():
            return True
        QMessageBox.information(self, "Clave necesaria", "Configura una clave de Gemini antes de generar descripciones")
        return self._open_settings() and bool(self.credentials.get())

    def _export(self, kind: str) -> None:
        filters = {
            "pdf": ("PDF (*.pdf)", ".pdf"),
            "docx": ("Documento Word (*.docx)", ".docx"),
            "json": ("JSON (*.json)", ".json"),
        }
        file_filter, suffix = filters[kind]
        path, _ = QFileDialog.getSaveFileName(self, "Exportar resultados", f"descripciones{suffix}", file_filter)
        if not path:
            return
        destination = Path(path)
        if destination.suffix.casefold() != suffix:
            destination = destination.with_suffix(suffix)
        try:
            if kind == "pdf":
                export_pdf(self.items, destination)
            elif kind == "docx":
                export_docx(self.items, destination)
            else:
                export_json(self.items, destination)
        except (ExportError, OSError) as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))
            return
        QMessageBox.information(self, "Exportacion completa", f"Archivo guardado en:\n{destination}")

    def _item(self, item_id: str) -> ImageItem | None:
        return next((item for item in self.items if item.id == item_id), None)

    def _refresh_ui(self) -> None:
        has_items = bool(self.items)
        busy = self.active_jobs > 0
        completed = sum(item.status == ImageStatus.COMPLETED and bool(item.description.strip()) for item in self.items)
        has_pending = any(
            item.status in {ImageStatus.PENDING, ImageStatus.ERROR, ImageStatus.CANCELLED}
            for item in self.items
        )
        self.empty_label.setVisible(not has_items)
        self.scroll.setVisible(has_items)
        self.count_label.setText(f"{len(self.items)} imagen{'es' if len(self.items) != 1 else ''} · {completed} lista{'s' if completed != 1 else ''}")
        self.generate_button.setEnabled(has_pending and not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy and not self.cancel_event.is_set())
        self.export_button.setEnabled(completed > 0 and not busy)
        self.progress.setVisible(busy or self.progress_hold)
        self.progress_label.setVisible(busy or self.progress_hold)
        self.drop_zone.setEnabled(not busy)
        self.add_images_button.setEnabled(not busy)
        self.add_zip_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.mode_combo.setEnabled(not busy)
        self.length_combo.setEnabled(not busy)
        self.context_edit.setEnabled(not busy)
        for card in self.cards.values():
            card.set_batch_busy(busy)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.active_jobs:
            answer = QMessageBox.question(
                self,
                "Cerrar ImgToText",
                "Hay imagenes en proceso. ¿Quieres cancelar y cerrar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_event.set()
            self.thread_pool.waitForDone(5000)
        self.importer.close()
        event.accept()


LIGHT_STYLE_SHEET = """
QWidget { font-family: "Segoe UI"; font-size: 10pt; color: #172033; }
QWidget#central { background: #f5f7fb; }
QDialog, QMessageBox { background: #f5f7fb; }
QMessageBox QLabel, QInputDialog QLabel { color: #172033; }
QLabel#appTitle { font-size: 25pt; font-weight: 700; color: #14213d; }
QLabel#appSubtitle, QLabel#dropHint, QLabel#cardMeta, QLabel#dialogNote { color: #667085; }
QLabel#progressLabel { color: #475467; font-weight: 600; }
QFrame#dropZone { background: #eef2ff; border: 2px dashed #8093f1; border-radius: 14px; }
QFrame#dropZone:disabled { background: #f1f3f6; border-color: #c6cad3; }
QLabel#dropTitle { font-size: 13pt; font-weight: 600; color: #3448a5; }
QFrame#controls, QFrame#imageCard { background: white; border: 1px solid #e1e5ee; border-radius: 12px; }
QLabel#cardTitle { font-size: 11pt; font-weight: 650; }
QLabel#countLabel { color: #475467; font-weight: 600; }
QLabel#emptyLabel { color: #98a2b3; font-size: 13pt; line-height: 1.5; }
QLabel#preview { background: #eef0f5; border-radius: 9px; }
QLabel#detailLabel { color: #6b4f16; background: #fff8e7; border-radius: 6px; padding: 6px; }
QLabel[status="pending"], QLabel[status="cancelled"] { color: #667085; background: #eef0f4; border-radius: 8px; padding: 4px 8px; }
QLabel[status="processing"] { color: #3049a8; background: #e9edff; border-radius: 8px; padding: 4px 8px; }
QLabel[status="completed"] { color: #176b45; background: #e7f7ef; border-radius: 8px; padding: 4px 8px; }
QLabel[status="error"] { color: #a43131; background: #fdecec; border-radius: 8px; padding: 4px 8px; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #ccd3df; border-radius: 8px; padding: 8px 13px; font-weight: 600; }
QPushButton:hover, QToolButton:hover { background: #f2f4f8; border-color: #aeb8c8; }
QPushButton:disabled, QToolButton:disabled { color: #a4a9b2; background: #f2f3f5; }
QPushButton#primaryButton { background: #4057d6; color: white; border-color: #4057d6; padding: 10px 18px; }
QPushButton#primaryButton:hover { background: #3248c3; }
QPushButton#secondaryButton { background: #eef2ff; color: #3448a5; border-color: #cbd4ff; }
QPushButton#quietButton { background: transparent; }
QPushButton#dangerButton { color: #a43131; border-color: #e0aaaa; }
QLineEdit, QTextEdit, QComboBox, QSpinBox { background: white; border: 1px solid #ccd3df; border-radius: 7px; padding: 7px; selection-background-color: #8093f1; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #6076e5; }
QComboBox QAbstractItemView { background: white; color: #172033; border: 1px solid #ccd3df; selection-background-color: #dfe5ff; selection-color: #172033; outline: 0; }
QScrollArea { background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QProgressBar { border: 1px solid #d2d7e0; border-radius: 7px; background: white; text-align: center; }
QProgressBar::chunk { background: #6076e5; border-radius: 6px; }
QMenu { background: white; color: #172033; border: 1px solid #d6dbe4; padding: 5px; }
QMenu::item { padding: 7px 28px 7px 12px; border-radius: 5px; }
QMenu::item:selected { background: #eef2ff; }
QToolTip { background: #172033; color: white; border: 1px solid #344054; padding: 5px; }
"""


DARK_STYLE_SHEET = """
QWidget { color: #e7eaf0; }
QWidget#central, QDialog, QMessageBox { background: #10141c; }
QMessageBox QLabel, QInputDialog QLabel { color: #eef1f6; }
QLabel#appTitle { color: #f7f8fb; }
QLabel#appSubtitle, QLabel#dropHint, QLabel#cardMeta, QLabel#dialogNote { color: #aab2c2; }
QLabel#progressLabel { color: #c6ccda; }
QLabel#countLabel { color: #c6ccda; }
QLabel#emptyLabel { color: #7e899c; }
QFrame#dropZone { background: #182039; border-color: #667eea; }
QFrame#dropZone:disabled { background: #171b23; border-color: #3c4452; }
QLabel#dropTitle { color: #aebaff; }
QFrame#controls, QFrame#imageCard { background: #191f2a; border-color: #303949; }
QLabel#preview { background: #10151e; }
QLabel#detailLabel { color: #f0cf83; background: #332a17; }
QLabel[status="pending"], QLabel[status="cancelled"] { color: #c0c6d1; background: #2a303b; }
QLabel[status="processing"] { color: #b6c2ff; background: #27315b; }
QLabel[status="completed"] { color: #8fe0b7; background: #193b2e; }
QLabel[status="error"] { color: #ffb2b2; background: #4a2529; }
QPushButton, QToolButton { background: #222a37; color: #edf0f5; border-color: #3b4658; }
QPushButton:hover, QToolButton:hover { background: #2b3545; border-color: #56647a; }
QPushButton:disabled, QToolButton:disabled { color: #6f7888; background: #191e27; border-color: #2b323e; }
QPushButton#primaryButton { background: #5b70e8; color: white; border-color: #6b7ff0; }
QPushButton#primaryButton:hover { background: #6b7ff0; }
QPushButton#secondaryButton { background: #242e55; color: #c6ceff; border-color: #46568e; }
QPushButton#quietButton { background: transparent; color: #dce1eb; }
QPushButton#quietButton:hover { background: #242b37; }
QPushButton#dangerButton { color: #ffb4b4; border-color: #77444a; }
QLineEdit, QTextEdit, QComboBox, QSpinBox { background: #111721; color: #f0f2f6; border-color: #3a4557; selection-background-color: #5267d6; selection-color: white; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #7185f0; }
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #7e8796; background: #171c24; }
QTextEdit:read-only { background: #151b25; }
QComboBox QAbstractItemView { background: #1a202b; color: #f0f2f6; border: 1px solid #465267; selection-background-color: #34447f; selection-color: white; outline: 0; }
QMenu { background: #1a202b; color: #eef1f6; border-color: #3a4557; }
QMenu::item:selected { background: #303d70; color: white; }
QProgressBar { color: #eef1f6; background: #171c25; border-color: #374153; }
QProgressBar::chunk { background: #6177eb; }
QToolTip { background: #e7eaf0; color: #11151d; border-color: #aeb6c4; }
QScrollBar:vertical { background: #151a22; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #3b4555; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #566276; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def build_style_sheet(dark: bool) -> str:
    return LIGHT_STYLE_SHEET + (DARK_STYLE_SHEET if dark else "")


STYLE_SHEET = LIGHT_STYLE_SHEET
