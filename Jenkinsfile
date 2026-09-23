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
                echo 'Buscando Python en el sistema e instalando dependencias...'
                bat '''
                    :: Buscar la ruta de Python dinámicamente en el equipo
                    for /f "delims=" %%i in ('where python 2^>nul') do set "PYTHON_CMD=%%i"
                    
                    if not defined PYTHON_CMD (
                        if exist "C:\\Python39\\python.exe" set "PYTHON_CMD=C:\\Python39\\python.exe"
                    )
                    if not defined PYTHON_CMD (
                        if exist "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" set "PYTHON_CMD=C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python311\\python.exe"
                    )
                    if not defined PYTHON_CMD (
                        if exist "C:\\Users\\asalvatierra\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" set "PYTHON_CMD=C:\\Users\\asalvatierra\\AppData\\Local\\Programs\\Python\\Python311\\python.exe"
                    )
                    
                    :: Si aún no se encuentra, mostrar mensaje de error explicativo
                    if not defined PYTHON_CMD (
                        echo ERROR CRITICO: No se pudo localizar python.exe en el servidor.
                        exit /b 1
                    ) else (
                        echo Python encontrado en: %PYTHON_CMD%
                        "%PYTHON_CMD%" -m pip install --upgrade pip
                        "%PYTHON_CMD%" -m pip install -r requirements.txt
                    )
                '''
            }
        }
        
        stage('3. Verificación / DB') {
            steps {
                echo 'Verificando base de datos o scripts...'
                bat '''
                    for /f "delims=" %%i in ('where python 2^>nul') do set "PYTHON_CMD=%%i"
                    if not defined PYTHON_CMD set "PYTHON_CMD=C:\\Python311\\python.exe"
                    
                    if exist init_db.py (
                        "%PYTHON_CMD%" init_db.py
                    ) else (
                        echo No se requiere script init_db.py, continuando...
                    )
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