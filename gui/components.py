
import sys
import requests
import base64
import json
import os
from urllib.parse import quote
from datetime import datetime

from PyQt6.QtWidgets import (
    QSizePolicy, QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QHBoxLayout, QGridLayout, QLineEdit, QComboBox, QTextEdit, QGroupBox,
    QTableWidget, QTableWidgetItem, QFormLayout
)
from PyQt6.QtMultimediaWidgets import QVideoWidget

from PyQt6.QtGui import QPixmap, QImage, QMovie, QColor, QPainter, QBrush, QPen
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QSize, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QMediaFormat, QMediaCaptureSession, QVideoSink
from gui.grilla_widget import GrillaWidget
from core import sdk_listener
from core.camera_checker import verificar_configuracion_grilla

CONFIG_FILE = "camaras_config.json"

class MainGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monitor PTZ Inteligente - Orca")
        self.setGeometry(100, 100, 1600, 900)

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)

        self.layout = QVBoxLayout()
        self.main_widget.setLayout(self.layout)

        self.grid_layout = QGridLayout()

        # Widgets de cámara y grilla
        self.video_widget1 = QLabel()
        self.video_widget1.setFixedSize(640, 480)
        self.video_widget1.setStyleSheet("background-color: black;")

        self.grilla_cam1 = GrillaWidget(parent=self.video_widget1)
        self.grilla_cam1.setGeometry(0, 0, 640, 480)
        self.grilla_cam1.raise_()

        self.grid_layout.addWidget(self.video_widget1, 0, 0)

        # Botón agregar cámara
        control_layout = QHBoxLayout()
        self.add_camera_btn = QPushButton("Agregar Cámara")
        self.add_camera_btn.clicked.connect(self.mostrar_formulario)
        control_layout.addWidget(self.add_camera_btn)
        self.layout.addLayout(self.grid_layout)
        self.layout.addLayout(control_layout)

        # Formulario oculto
        self.add_camera_form = QGroupBox("Nueva Cámara")
        self.form_layout = QFormLayout()
        self.cam_ip = QLineEdit()
        self.cam_usuario = QLineEdit()
        self.cam_contrasena = QLineEdit()
        self.cam_tipo = QComboBox()
        self.cam_tipo.addItems(["fija", "ptz", "nvr"])
        self.cam_canal = QLineEdit("0")
        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(self.conectar_camara)

        self.form_layout.addRow("IP:", self.cam_ip)
        self.form_layout.addRow("Usuario:", self.cam_usuario)
        self.form_layout.addRow("Contraseña:", self.cam_contrasena)
        self.form_layout.addRow("Tipo:", self.cam_tipo)
        self.form_layout.addRow("Canal:", self.cam_canal)
        self.form_layout.addRow(self.connect_btn)

        self.add_camera_form.setLayout(self.form_layout)
        self.layout.addWidget(self.add_camera_form)
        self.add_camera_form.hide()

        # Video setup
        self.media_player = QMediaPlayer()
        self.video_sink = QVideoSink()
        self.media_player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.manejar_frame_video)
        self.video_widget1.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Establecer etiqueta como destino de los frames
        self.video_sink_widget = self.video_widget1

    def mostrar_formulario(self):
        self.add_camera_form.setVisible(not self.add_camera_form.isVisible())

    def conectar_camara(self):
        ip = self.cam_ip.text()
        usuario = self.cam_usuario.text()
        contrasena = self.cam_contrasena.text()
        canal = self.cam_canal.text()
        tipo = self.cam_tipo.currentText()
        puerto = 554
        contrasena_encoded = quote(contrasena)

        if tipo == "nvr":
            url = f"rtsp://{usuario}:{contrasena_encoded}@{ip}:{puerto}/unicast/c{canal}/s1/live"
        else:
            url = f"rtsp://{usuario}:{contrasena_encoded}@{ip}:{puerto}/Streaming/Channels/{canal}"

        self.media_player.setSource(QUrl(url))
        self.media_player.play()

    def manejar_frame_video(self, frame):
        if frame.isValid():
            image = frame.toImage()
            pixmap = QPixmap.fromImage(image)
            self.video_widget1.setPixmap(pixmap)
