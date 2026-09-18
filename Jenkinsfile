pipeline {
    agent any

    stages {
        stage('1. Preparación del Entorno') {
            steps {
                echo 'Limpiando entorno de trabajo...'
                cleanWs()
            }
        }

        stage('2. Instalar Dependencias') {
            steps {
                echo 'Instalando dependencias del Backend...'
                sh 'npm ci --prefer-offline || npm install'
            }
        }

        stage('3. Pruebas Automatizadas') {
            steps {
                echo 'Ejecutando pruebas del Backend...'
                // Genera reporte de pruebas en formato JUnit para la gráfica
                sh 'npm run test -- --reporter=junit --outputFile=test-report.xml || true'
            }
        }

        stage('4. Respaldos y Mantenimiento') {
            steps {
                echo 'Creando copia de respaldo previa al despliegue...'
                sh 'tar -czf backup-backend-$(date +%Y%m%d_%H%M%S).tar.gz /var/www/html/idec-erp-back || true'
            }
        }

        stage('5. Despliegue en Servidor') {
            steps {
                echo 'Sincronizando archivos del Backend...'
                sh 'rsync -avz --exclude="node_modules" --exclude=".git" ./ /var/www/html/idec-erp-back/'
                
                echo 'Reiniciando el servicio de backend (PM2 / Node)...'
                sh 'pm2 restart idec-erp-back || true'
            }
        }
    }

    post {
        always {
            echo 'Publicando resultados de las pruebas...'
            // Genera y actualiza la gráfica de tendencias
            junit allowEmptyResults: true, testResults: '**/test-report.xml'
            
            echo 'Limpiando espacio de trabajo...'
            cleanWs()
        }
        success {
            echo '¡El despliegue del Backend se completó con éxito!'
        }
        failure {
            echo 'El pipeline del Backend ha fallado.'
        }
    }
}