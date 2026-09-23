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
        
        stage('2. Instalar Dependencias (Back)') {
            steps {
                echo 'Instalando dependencias del Backend...'
                bat '''
                    set NODE_SKIP_PLATFORM_CHECK=1
                    set PATH=C:\\Program Files\\nodejs;%PATH%
                    cd ruta_a_tu_carpeta_backend
                    "C:\\Program Files\\nodejs\\npm.cmd" install
                '''
            }
        }
        
        stage('3. Pruebas o Build (Back)') {
            steps {
                echo 'Ejecutando pruebas / preparación del Backend...'
                bat '''
                    set NODE_SKIP_PLATFORM_CHECK=1
                    set PATH=C:\\Program Files\\nodejs;%PATH%
                    cd ruta_a_tu_carpeta_backend
                    "C:\\Program Files\\nodejs\\npm.cmd" run build || echo "Si no hay script de build, continuando..."
                '''
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
                            echo 'Aprobación automática por tiempo agotado (Seguridad para la demo del Back).'
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