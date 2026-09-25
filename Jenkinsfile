pipeline {
    agent {
        label 'windows-runner'
    }
    parameters {
        booleanParam(name: 'EJECUTAR_AUTOMATICO', defaultValue: true, description: 'Ejecución fluida automática')
    }
    triggers {
        cron('30 2 * * *')
    }
    stages {
        stage('Preparación') {
            steps {
                cleanWs()
                checkout scm
            }
        }
        stage('Instalar Dependencias') {
            steps {
                bat '"C:\\Program Files\\Python311\\python.exe" -m pip install --upgrade pip'
                bat '"C:\\Program Files\\Python311\\python.exe" -m pip install -r requirements.txt'
            }
        }
        stage('Pruebas y Verificación') {
            steps {
                script {
                    env.PYTHONIOENCODING = "utf-8"
                }
                bat '"C:\\Program Files\\Python311\\python.exe" -X utf8 -c "import app.main; print(\'¡La app del backend cargo con exito!\')"'
            }
        }
        stage('Desplegar a IIS') {
            steps {
                echo 'Copiando archivos del backend a IIS...'
                // Copia los archivos del proyecto a la carpeta de IIS de forma recursiva y forzada
                bat 'xcopy /E /Y /I "%WORKSPACE%\\*" "C:\\inetpub\\wwwroot\\siscatJenkins\\"'
            }
        }
    }
    post {
        success {
            echo '¡El pipeline del Backend se ejecutó y desplegó con éxito!'
        }
        failure {
            echo 'El pipeline del Backend ha fallado. Revise la consola.'
        }
    }
}