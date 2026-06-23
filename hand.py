import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from GUI import MainWindow, load_stylesheet      
from communication import RobotCommThread, wire_comm_to_gui

ESP32_HOST = "192.168.4.1"   
ESP32_PORT = 8080              

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet())
    
    win = MainWindow()
    comm = RobotCommThread(host=ESP32_HOST, port=ESP32_PORT)
    
    wire_comm_to_gui(win, comm)
    
    comm.start()
    win.show()

    app.aboutToQuit.connect(comm.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()