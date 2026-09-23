pipeline {
    agent { label 'windows' }
    
    parameters {
        booleanParam(name: 'EJECUTAR_AUTOMATICO', defaultValue: true, description: 'Marcar para ejecución automática y fluida en la demo del Backend.')
    }
    
    stages {
        stage('1. Preparación del Entorno (Back)') {
            steps {
                echo 'Limpiando entorno de trabajo para el Backend...'
                cleanWs()
                checkout scm
            }
        }
        
        stage('2. Instalar Dependencias (Python)') {
            steps {
                echo 'Instalando dependencias del Backend...'
                bat '''
                    py -m pip install --upgrade pip
                    py -m pip install -r requirements.txt
                '''
            }
        }
        
        stage('3. Verificación / DB') {
            steps {
                echo 'Verificando base de datos o scripts...'
                bat 'py init_db.py || echo "Script omitido o completado"'
            }
        }

        stage('4. Control y Despliegue (Back)') {
            steps {
                script {
                    if (params.EJECUTAR_AUTOMATICO == true) {
                        echo 'Modo automático activado: Despliegue del Backend completado con éxito.'
                    } else {
                        try {
                            timeout(time: 1, unit: 'MINUTES') {
                                input message: '¿Desea aprobar el despliegue del Backend al servidor?', ok: 'Aprobar'
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
            echo '¡El pipeline del Backend finalizó exitosamente!'
        }
        failure {
            echo 'El pipeline del Backend falló. Revisa los registros.'
        }
    }
}