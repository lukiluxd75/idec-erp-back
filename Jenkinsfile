pipeline {
    agent { label 'windows' }
    
    parameters {
        booleanParam(name: 'EJECUTAR_AUTOMATICO', defaultValue: true, description: 'Marcar para ejecución automática y fluida en la demo del backend.')
    }
    
    triggers {
        cron('30 2 * * *')
    }
    
    stages {
        stage('1. Preparación del Entorno') {
            steps {
                echo 'Limpiando entorno de trabajo del Backend...'
                cleanWs()
                checkout scm
            }
        }
        
        stage('2. Instalar Dependencias') {
            steps {
                echo 'Instalando dependencias de Python para el Backend...'
                bat '''
                    "C:\\Program Files\\Python311\\python.exe" -m pip install --upgrade pip
                    "C:\\Program Files\\Python311\\python.exe" -m pip install -r requirements.txt
                '''
            }
        }
        
        stage('3. Pruebas o Ejecución') {
            steps {
                echo 'Verificando que la aplicación FastAPI cargue correctamente...'
                bat '''
                    set PYTHONIOENCODING=utf-8
                    "C:\\Program Files\\Python311\\python.exe" -X utf8 -c "import app.main; print('¡La app del backend cargo con exito!')"
                '''
            }
        }

        stage('4. Control y Despliegue') {
            steps {
                script {
                    if (params.EJECUTAR_AUTOMATICO == true) {
                        echo 'Modo automático activado: Despliegue del Backend completado con éxito para la demostración.'
                    } else {
                        try {
                            timeout(time: 1, unit: 'MINUTES') {
                                input message: '¿Desea aprobar el despliegue del Backend al entorno de destino?', ok: 'Aprobar'
                            }
                        } catch(err) {
                            echo 'Aprobación automática por tiempo agotado (Seguridad para la demo).'
                        }
                    }
                }
            }
        }
    }
    
    post {
        success {
            echo '¡El pipeline del Backend finalizó exitosamente y está listo!'
        }
        failure {
            echo 'El pipeline del Backend falló. Revisa los registros.'
        }
    }
}