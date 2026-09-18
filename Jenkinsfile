pipeline {
    agent {
        node {
            label 'principal'
        }
    }
    stages {
        stage('Desplegar ERP Back') {
            steps {
                sh '''
                echo "Desplegando automáticamente la rama ${BRANCH_NAME}..."
                mkdir -p /tmp/erp-back-pruebas
                rsync -avz --exclude='.git' ./ /tmp/erp-back-pruebas/
                echo "Despliegue del Backend completado con éxito."
                '''
            }
        }
    }
}