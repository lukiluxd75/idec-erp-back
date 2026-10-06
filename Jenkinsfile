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
                powershell '''
                $ErrorActionPreference = "Stop"
                $pythonExe = "C:\\Program Files\\Python311\\python.exe"

                Write-Host "Usando Python en: $pythonExe"
                & "$pythonExe" -m pip install --upgrade pip

                if (Test-Path "requirements.txt") {
                    Write-Host "Instalando dependencias desde requirements.txt..."
                    & "$pythonExe" -m pip install -r requirements.txt
                } else {
                    Write-Host "ADVERTENCIA: No se encontró requirements.txt"
                }
                '''
            }
        }
        
        stage('Pruebas y Verificación') {
            steps {
                powershell '''
                $ErrorActionPreference = "Stop"
                $env:PYTHONIOENCODING = "utf-8"
                $env:PYTHONPATH = "$PWD"
                $pythonExe = "C:\\Program Files\\Python311\\python.exe"
                
                Write-Host "Verificando importación del módulo app.main..."
                & "$pythonExe" -X utf8 -c "import app.main; print('¡La app del backend cargo con exito!')"
                '''
            }
        }
        
        stage('Desplegar a IIS') {
            steps {
                powershell '''
                $targetDir = "C:\\inetpub\\wwwroot\\siscatJenkins"
                
                Write-Host "Copiando archivos a IIS en $targetDir..."
                if (-not (Test-Path $targetDir)) {
                    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
                }

                # /MIR es un espejo: borra del servidor todo lo que no venga del
                # repositorio. Lo que vive SOLO en el servidor hay que excluirlo o
                # desaparece en cada despliegue:
                #   .env        las variables reales (nunca se versionan). Sin él la
                #               app vuelve a sus valores por defecto: FRONTEND_ORIGIN
                #               pasa a ser localhost y el navegador bloquea al front
                #               por CORS, y además se queda sin base y sin Keycloak.
                #   web.config  la configuración del sitio en IIS, que no está en el repo.
                #   data        lo que la app genera trabajando (recortes, exportaciones).
                $process = Start-Process robocopy -ArgumentList "`"$PWD`" `"$targetDir`" /MIR /XD .git .venv __pycache__ data /XF Jenkinsfile .env web.config /R:2 /W:1 /NJH /NJS" -Wait -NoNewWindow -PassThru
                
                if ($process.ExitCode -le 7) {
                    Write-Host "Despliegue a IIS completado con éxito."
                    exit 0
                } else {
                    Write-Error "Error en Robocopy al copiar a IIS. Código de salida: $($process.ExitCode)"
                    exit $process.ExitCode
                }
                '''
            }
        }
    }
    post {
        success {
            echo '¡El pipeline del Backend se ejecutó y desplegó con éxito!'
        }
        failure {
            echo 'El pipeline del Backend ha fallado. Revisa la consola.'
        }
    }
}