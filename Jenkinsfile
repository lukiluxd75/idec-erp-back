pipeline {
    agent { label 'principal' }

    stages {
        stage('1. Preparación del Entorno') {
            steps {
                echo 'Limpiando entorno de trabajo...'
                cleanWs()
                checkout scm
            }
        }

        stage('2. Instalar Dependencias') {
            steps {
                echo 'Instalando dependencias de Python...'
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }

        stage('3. Despliegue') {
            steps {
                echo 'Preparando entorno de ejecución...'
            }
        }
    }
}