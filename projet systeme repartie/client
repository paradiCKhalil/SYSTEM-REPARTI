importsocket
importpsutil
importtime
importjson
importplatform
importos

SERVER_IP = '127.0.0.1 #IPdu serveur central
SERVER_PORT = 5000

defget_metrics():
    #Collectedesmétriques
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    #Simulerlestatutdeservices  (6 choisis )
    services = {'ssh': Truenginx :' False db': True chrome: Truedocker':True 'firewall':True}
    
    # Vérification de 4 ports (ex:22, 80, 443, 3306)
    ports = {22: True, 80: False, 443: True, 3306: False}
    
    metrics = {
        'node_id': platform.node()'os': platform.system()'cpu': cpu'memory': memory' disk': disk'alert': cpu > 90 or memory > 90'services': services'ports': ports
    }
    return metrics

def run_agent():
    while True:
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((SERVER_IP, SERVER_PORT))
            
            data = get_metrics()
            client_socket.send(json.dumps(data).encode('utf-8'))
            client_socket.close()
            print(f"Données envoyées : {data['node_id']}")
            
        except Exception as e:
            print(f"Erreur : {e}")
        
        time.sleep(10) # Envoi toutes les 10 secondes

if __name__ == '__main__':
    run_agent()
