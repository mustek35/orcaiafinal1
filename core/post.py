from flask import Flask, request

app = Flask(__name__)

@app.route('/alarms', methods=['POST'])
def receive_alarm():
    data = request.get_json()
    print("📥 Evento recibido:", data)
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
