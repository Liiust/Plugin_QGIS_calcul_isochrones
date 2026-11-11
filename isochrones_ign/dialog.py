"""
PyQt dialog (built in code, without a .ui file) -> All logic contained in controller.py
"""

# Liiust

from __future__ import annotations

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsTask
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout,
)

from .api import GeoplateformeError, Options
from .controller import IsochroneController
from .layer_builder import add_isochrone_layer

TITLE = "Isochrones IGN"


class IsochroneDialog(QDialog):
    def __init__(self, iface, controller=None, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.controller = controller or IsochroneController()
        self._task = None  # reference to be kept as long as the task is running

        self.setWindowTitle("Isochrone / isodistance computing (IGN Géoplatforme)")
        self.point_edit = QLineEdit()
        self.point_edit.setPlaceholderText("lon,lat (EPSG:4326)")
        self.btn_pick = QPushButton("Pick on map")
        self.resource = QComboBox()
        self.cost_type = QComboBox()
        self.cost_value = QDoubleSpinBox()
        self.cost_value.setRange(0.1, 1_000_000)
        self.cost_value.setDecimals(1)
        self.cost_value.setValue(10)
        self.profile = QComboBox()
        self.direction = QComboBox()
        self.time_unit = QComboBox()
        self.distance_unit = QComboBox()
        self.constraints = QLineEdit()
        self.constraints.setPlaceholderText("optional (JSON)")
        self.btn_caps = QPushButton("Reload service options")
        self.btn_compute = QPushButton("Compute")
        self.btn_close = QPushButton("Close")

        row = QHBoxLayout()
        row.addWidget(self.point_edit)
        row.addWidget(self.btn_pick)
        form = QFormLayout()
        form.addRow("Point", row)
        form.addRow("Resource", self.resource)
        form.addRow("Cost type", self.cost_type)
        form.addRow("Cost value", self.cost_value)
        form.addRow("Profile", self.profile)
        form.addRow("Direction", self.direction)
        form.addRow("Unit of time", self.time_unit)
        form.addRow("Unit of distance", self.distance_unit)
        form.addRow("Constraints", self.constraints)
        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_caps)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_compute)
        buttons.addWidget(self.btn_close)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(buttons)

        self.map_tool = QgsMapToolEmitPoint(self.canvas)
        self.map_tool.canvasClicked.connect(self._on_canvas_clicked)
        self.btn_pick.clicked.connect(self.pick_point)
        self.btn_caps.clicked.connect(self.load_options)
        self.btn_compute.clicked.connect(self.on_compute)
        self.btn_close.clicked.connect(self.close)
        self.resource.currentTextChanged.connect(self._on_resource_changed)

        self._fill(self.controller.options)  # default values, before any network call
        self.load_options()

    # -- options ---------------------------------------------------------- #
    @staticmethod
    def _set_items(combo: QComboBox, values, default=None):
        current = combo.currentText()
        combo.clear()
        combo.addItems(values)
        wanted = current or default
        if wanted in values:
            combo.setCurrentText(wanted)

    def _fill(self, o: Options):
        """Fill the list of isochrone-compatible resources (excluding OSRM, etc.)."""
        self._set_items(self.resource, o.ids(), o.default_resource())
        self._on_resource_changed(self.resource.currentText())

    def _on_resource_changed(self, rid: str):
        """The available settings depend on the chosen resource."""
        ro = self.controller.options.for_resource(rid)
        if ro is None:
            return
        self._set_items(self.cost_type, ro.cost_types, "time")
        self._set_items(self.profile, ro.profiles, "car")
        self._set_items(self.direction, ro.directions, "departure")
        # ' standard ' : display format hh:mm:ss, not a unit for entering a cost
        self._set_items(self.time_unit, [u for u in ro.time_units if u != "standard"], "minute")
        self._set_items(self.distance_unit, ro.distance_units, "meter")
        if ro.cost_value_max:
            self.cost_value.setMaximum(float(ro.cost_value_max))
        self.resource.setToolTip(ro.description)
        if ro.point_bbox:
            x0, y0, x1, y1 = ro.point_bbox
            self.point_edit.setToolTip(f"Covered area : lon {x0:.2f} to {x1:.2f}, lat {y0:.2f} à {y1:.2f}")
        example = self.controller.constraint_example(rid)
        self.constraints.setPlaceholderText(f"optional, e.g. {example}" if example else "no constraints available")
        self.constraints.setToolTip(self.controller.constraint_help(rid))

    def load_options(self):
        def done(options):
            self.controller.options = options
            self._fill(options)
            self.iface.messageBar().pushSuccess(TITLE, "Service options loaded.")

        self._background("Isochrones IGN : getCapabilities", self.controller.client.get_options, done)

    # -- point ------------------------------------------------------------ #
    def pick_point(self):
        self.hide()
        self.canvas.setMapTool(self.map_tool)

    def _on_canvas_clicked(self, point, button):
        src = self.canvas.mapSettings().destinationCrs()
        dst = QgsCoordinateReferenceSystem("EPSG:4326")
        p = QgsCoordinateTransform(src, dst, QgsProject.instance()).transform(point)
        self.point_edit.setText(f"{p.x():.6f},{p.y():.6f}")
        self.canvas.unsetMapTool(self.map_tool)
        self.show()
        self.raise_()
        self.activateWindow()

    # -- calcul ----------------------------------------------------------- #
    def read_form(self) -> dict:
        return {
            "point": self.point_edit.text(),
            "resource": self.resource.currentText(),
            "cost_type": self.cost_type.currentText(),
            "cost_value": self.cost_value.value(),
            "profile": self.profile.currentText(),
            "direction": self.direction.currentText(),
            "time_unit": self.time_unit.currentText(),
            "distance_unit": self.distance_unit.currentText(),
            "constraints": self.constraints.text(),
        }

    def on_compute(self):
        form = self.read_form()
        try:
            self.controller.build_request(form)  # immediate validation, main thread
        except GeoplateformeError as exc:
            self.iface.messageBar().pushWarning(TITLE, str(exc))
            return

        def done(result):
            layer = add_isochrone_layer(result.feature_collection, result.name, result.request.crs)
            xform = QgsCoordinateTransform(layer.crs(), self.canvas.mapSettings().destinationCrs(), QgsProject.instance())
            self.canvas.setExtent(xform.transformBoundingBox(layer.extent()))
            self.canvas.refresh()
            self.iface.messageBar().pushSuccess(TITLE, f"Layer ' {result.name} ' added.")

        self._background("Isochrones IGN : Computing", lambda: self.controller.compute(form), done)

    # -- background task -------------------------------------------- #
    def _set_busy(self, busy: bool):
        for w in (self.btn_compute, self.btn_caps, self.btn_pick):
            w.setEnabled(not busy)

    def _background(self, description, fn, on_ok):
        def finished(exception, value=None):  # executed in the main thread
            self._set_busy(False)
            if exception is not None:
                self.iface.messageBar().pushCritical(TITLE, str(exception))
                return
            try:
                on_ok(value)
            except Exception as exc:  # noqa: BLE001
                self.iface.messageBar().pushCritical(TITLE, str(exc))

        self._set_busy(True)
        self._task = QgsTask.fromFunction(description, lambda task: fn(), on_finished=finished)
        QgsApplication.taskManager().addTask(self._task)
