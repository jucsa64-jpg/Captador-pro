# ========================================
# CAPTADORPRO - SISTEMA COMPLETO PARA RENDER
# ========================================

from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from datetime import datetime
import uuid
import json
import requests
import os

app = Flask(__name__)
CORS(app)

# ========================================
# CONFIGURACIÓN DESDE VARIABLES DE ENTORNO
# ========================================

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
TU_ZONA = os.environ.get('TU_ZONA', 'Garraf')

AUTONOMOS = {
    "autonomo1": {
        "nombre": os.environ.get('AUTONOMO_NOMBRE', 'Pablo'),
        "nif": "12345678A",
        "telefono": "+34600111222",
        "especialidad": "fontaneria",
        "tarifa_hora": 45,
        "desplazamiento": 15,
        "margen_materiales": 0.35,
        "comision_tuya": 0.25,
        "zona": ["Sitges", "Vilanova", "Cubelles", "Garraf"],
        "activo": True
    }
}

RECARGOS_URGENCIA = {
    "normal": 1.0,
    "urgente": 1.35,
    "noche": 1.50,
    "festivo": 1.60,
    "nocturno_festivo": 1.80
}

AVISOS_ACTIVOS = []

# ========================================
# FUNCIONES
# ========================================

def detectar_nivel_urgencia(texto, es_urgente):
    hora = datetime.now().hour
    dia = datetime.now().weekday()
    es_noche = hora < 8 or hora >= 20
    es_festivo = dia >= 5
    
    if es_noche and es_festivo and es_urgente:
        return "nocturno_festivo"
    elif es_noche and es_urgente:
        return "noche"
    elif es_festivo and es_urgente:
        return "festivo"
    elif es_urgente:
        return "urgente"
    return "normal"

def calcular_presupuesto(autonomo_id, horas, urgencia):
    auto = AUTONOMOS[autonomo_id]
    recargo = RECARGOS_URGENCIA[urgencia]
    
    materiales = 85 * (1 + auto["margen_materiales"])
    mano_obra = horas * auto["tarifa_hora"] * recargo
    desplazamiento = auto["desplazamiento"] * recargo
    
    subtotal = materiales + mano_obra + desplazamiento
    comision = subtotal * auto["comision_tuya"]
    total = subtotal + comision
    
    min_precio = round(total * 0.8 / 10) * 10
    max_precio = round(total * 1.2 / 10) * 10
    
    return {
        "autonomo": auto["nombre"],
        "rango_minimo": int(min_precio),
        "rango_maximo": int(max_precio),
        "comision_min": round(min_precio * auto["comision_tuya"] / (1 + auto["comision_tuya"]), 2),
        "comision_max": round(max_precio * auto["comision_tuya"] / (1 + auto["comision_tuya"]), 2),
        "urgencia": urgencia,
        "recargo": f"+{int((recargo-1)*100)}%" if recargo > 1 else "Sin recargo"
    }

def notificar_telegram(aviso):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado")
        return
    
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    url_app = request.host_url
    
    # Alarma
    try:
        requests.post(f"{url_base}/sendAudio", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "audio": "https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg",
            "title": f"🚨 NUEVO AVISO {aviso['urgencia'].upper()}",
            "disable_notification": False
        }, timeout=5)
    except:
        pass
    
    # Alerta
    try:
        requests.post(f"{url_base}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "🚨🚨🚨 NUEVO AVISO URGENTE 🚨🚨🚨",
            "disable_notification": False
        }, timeout=5)
    except:
        pass
    
    # Detalles
    mensaje = f"""📋 <b>{aviso['problema'][:100]}</b>

📍 Zona: <b>{aviso['zona']}</b>
📞 Cliente: {aviso.get('cliente_telefono', 'Sin teléfono')}

💰 <b>Presupuesto: {aviso['presupuesto_min']}-{aviso['presupuesto_max']}€</b>
💵 Comisión: <b>{aviso['comision_min']}-{aviso['comision_max']}€</b>

⚡ Aviso #{aviso['id']}
⏰ Urgencia: <b>{aviso['urgencia'].upper()}</b>

🔗 <a href="{url_app}">ABRIR APP</a>"""
    
    try:
        requests.post(f"{url_base}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensaje,
            "parse_mode": "HTML",
            "disable_notification": False
        }, timeout=5)
    except:
        pass
    
    # Botón
    try:
        requests.post(f"{url_base}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"⏰ HAZ CLIC PARA RESPONDER #{aviso['id']}",
            "reply_markup": {"inline_keyboard": [[{"text": "🔗 ABRIR APP", "url": url_app}]]},
            "disable_notification": False
        }, timeout=5)
    except:
        pass

def procesar_aviso(texto, zona="", telefono=None):
    aviso_id = str(uuid.uuid4())[:8].upper()
    
    texto_lower = texto.lower()
    if "aire" in texto_lower or "clima" in texto_lower:
        tipo = "clima"
    elif "gas" in texto_lower:
        tipo = "gas"
    else:
        tipo = "fontaneria"
    
    urgente = any(p in texto_lower for p in ["urgente", "ya", "roto", "fuga"])
    nivel_urgencia = detectar_nivel_urgencia(texto, urgente)
    
    autonomo_id = list(AUTONOMOS.keys())[0]
    presupuesto = calcular_presupuesto(autonomo_id, 2.0, nivel_urgencia)
    
    aviso = {
        "id": aviso_id,
        "autonomo_id": autonomo_id,
        "problema": texto[:100],
        "zona": zona or TU_ZONA,
        "presupuesto_min": presupuesto["rango_minimo"],
        "presupuesto_max": presupuesto["rango_maximo"],
        "comision_min": presupuesto["comision_min"],
        "comision_max": presupuesto["comision_max"],
        "urgencia": nivel_urgencia,
        "cliente_telefono": telefono,
        "estado": "pendiente_aceptacion",
        "fecha": datetime.now().isoformat()
    }
    
    AVISOS_ACTIVOS.append(aviso)
    notificar_telegram(aviso)
    
    return aviso, presupuesto

# ========================================
# RUTAS WEB
# ========================================

HTML_APP = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CaptadorPro</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea, #764ba2); padding: 20px; border-radius: 12px; margin-bottom: 20px; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 15px; }
        .urgente { border-left: 4px solid #ef4444; }
        .normal { border-left: 4px solid #3b82f6; }
        .btn { padding: 12px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; width: 100%; margin-top: 10px; }
        .btn-ok { background: #10b981; color: white; }
        .btn-no { background: #ef4444; color: white; }
        .precio { font-size: 1.8em; color: #10b981; font-weight: bold; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; }
        .badge-urgente { background: #fecaca; color: #991b1b; }
        .badge-normal { background: #dbeafe; color: #1e40af; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔧 CaptadorPro</h1>
        <p id="estado">Cargando...</p>
    </div>
    <div id="avisos">Cargando...</div>
    <script>
        function cargar() {
            fetch('/api/avisos')
                .then(r => r.json())
                .then(data => {
                    const c = document.getElementById('avisos');
                    if (data.avisos.length === 0) {
                        c.innerHTML = '<p style="text-align:center;color:#64748b;">📭 No hay avisos</p>';
                        document.getElementById('estado').textContent = 'Sin avisos';
                        return;
                    }
                    document.getElementById('estado').textContent = data.avisos.length + ' avisos';
                    c.innerHTML = data.avisos.map(a => `
                        <div class="card ${a.urgencia === 'normal' ? 'normal' : 'urgente'}">
                            <span class="badge badge-${a.urgencia === 'normal' ? 'normal' : 'urgente'}">${a.urgencia.toUpperCase()}</span>
                            <span style="color:#94a3b8;">#${a.id}</span>
                            <h3 style="margin:15px 0 10px;">📋 ${a.problema}</h3>
                            <p style="color:#cbd5e1;margin-bottom:15px;">📍 ${a.zona}<br>📞 ${a.cliente_telefono || 'Sin teléfono'}</p>
                            <div class="precio">${a.presupuesto_min}-${a.presupuesto_max}€</div>
                            <p style="color:#fbbf24;margin-top:10px;">💰 Comisión: ${a.comision_min}-${a.comision_max}€</p>
                            <button class="btn btn-ok" onclick="aceptar('${a.id}')">✅ ACEPTAR</button>
                            <button class="btn btn-no" onclick="rechazar('${a.id}')">❌ RECHAZAR</button>
                        </div>
                    `).join('');
                });
        }
        function aceptar(id) {
            if(!confirm('¿Aceptar?')) return;
            fetch('/api/aceptar/'+id, {method:'POST'}).then(() => { alert('✅ Aceptado'); cargar(); });
        }
        function rechazar(id) {
            if(!confirm('¿Rechazar?')) return;
            fetch('/api/rechazar/'+id, {method:'POST'}).then(() => { alert('Rechazado'); cargar(); });
        }
        cargar();
        setInterval(cargar, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_APP)

@app.route('/api/avisos')
def get_avisos():
    avisos = [a for a in AVISOS_ACTIVOS if a.get('estado') == 'pendiente_aceptacion']
    return jsonify({"avisos": avisos})

@app.route('/api/aceptar/<aviso_id>', methods=['POST'])
def aceptar(aviso_id):
    for a in AVISOS_ACTIVOS:
        if a['id'] == aviso_id:
            a['estado'] = 'aceptado'
            return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route('/api/rechazar/<aviso_id>', methods=['POST'])
def rechazar(aviso_id):
    for a in AVISOS_ACTIVOS:
        if a['id'] == aviso_id:
            a['estado'] = 'rechazado'
            return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

@app.route('/webhook/aviso', methods=['POST'])
def webhook_aviso():
    """Endpoint para recibir avisos externos (formularios, WhatsApp, etc)"""
    data = request.json
    aviso, presupuesto = procesar_aviso(
        texto=data.get('texto', ''),
        zona=data.get('zona', ''),
        telefono=data.get('telefono')
    )
    return jsonify({
        "ok": True,
        "aviso_id": aviso['id'],
        "presupuesto": presupuesto
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok", "avisos": len(AVISOS_ACTIVOS)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
