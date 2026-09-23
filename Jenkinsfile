pipeline {
    agent any

    stages {
        stage('Verificar Entorno') {
            steps {
                echo 'Verificando versiones de Node y Python...'
                bat 'node -v'
                bat '"C:\\Program Files\\Python311\\python.exe" --version'
            }
        }

        stage('Instalar Dependencias') {
            steps {
                echo 'Instalando las dependencias del backend con pip...'
                // Si tu archivo de dependencias tiene otro nombre (ej. setup.py), ajusta esta línea
                bat '"C:\\Program Files\\Python311\\python.exe" -m pip install --upgrade pip'
                bat '"C:\\Program Files\\Python311\\python.exe" -m pip install -r requirements.txt'
            }
        }

        stage('Ejecutar Pruebas o Servidor') {
            steps {
                echo 'Ejecutando el proyecto backend...'
                // Cambia 'main.py' por el archivo principal con el que arranca tu proyecto de Python
                bat '"C:\\Program Files\\Python311\\python.exe" main.py'
            }
        }
    }

    post {
        success {
            echo '¡El pipeline del backend se ejecutó exitosamente!'
        }
        failure {
            echo 'Hubo un error en alguna de las etapas del backend.'
        }
    }
}