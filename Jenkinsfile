def notifyDiscord(String esito) {
    withCredentials([string(credentialsId: 'discord-webhook', variable: 'WEBHOOK')]) {
        def msg = "${esito} **${env.JOB_NAME}** #${env.BUILD_NUMBER} (commit ${env.IMAGE_TAG})\\n${env.BUILD_URL}"
        sh """
            curl -fsS -H 'Content-Type: application/json' \
              -d '{"content": "${msg}"}' \
              "\$WEBHOOK"
        """
    }
}

pipeline {
    agent any

    options {
        skipDefaultCheckout()                           // il checkout lo facciamo noi, nello stage dedicato
        buildDiscarder(logRotator(numToKeepStr: '10'))  // conserva solo le ultime 10 build
    }

    environment {
        IMAGE_NAME     = 'sentiment-api'
        CONTAINER_NAME = 'sentiment-api'
        DOCKER_NETWORK = 'monitoring'
        APP_PORT       = '8000'
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.IMAGE_TAG = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
                }
                echo "Branch: ${env.BRANCH_NAME} - Commit: ${env.IMAGE_TAG}"
            }
        }

        stage('Build') {
            steps {
                sh "docker build -t ${IMAGE_NAME}:${IMAGE_TAG} ."
            }
        }

        stage('Test') {
            steps {
                sh "docker run --name test-${IMAGE_TAG} ${IMAGE_NAME}:${IMAGE_TAG} pytest -v --junitxml=/tmp/report.xml"
            }
            post {
                always {
                    sh "docker cp test-${IMAGE_TAG}:/tmp/report.xml report.xml || true"
                    sh "docker rm -f test-${IMAGE_TAG} || true"
                    junit allowEmptyResults: true, testResults: 'report.xml'
                }
            }
        }
        stage('Security scan') {
            steps {
                sh """
                    docker run --rm --user root ${IMAGE_NAME}:${IMAGE_TAG} \
                      sh -c "pip install -q pip-audit && pip-audit -r requirements.txt --no-deps --disable-pip"
                """
            }
        }

        stage('Deploy') {
            when { branch 'main' }
            steps {
                sh "docker network create ${DOCKER_NETWORK} || true"
                sh "docker rm -f ${CONTAINER_NAME} || true"
                sh """
                    docker run -d --name ${CONTAINER_NAME} \
                      --network ${DOCKER_NETWORK} \
                      -p ${APP_PORT}:8000 \
                      --restart unless-stopped \
                      ${IMAGE_NAME}:${IMAGE_TAG}
                """
                sh "docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${IMAGE_NAME}:latest"
            }
        }

        stage('Smoke test') {
            when { branch 'main' }
            steps {
                sh """
                    curl -fsS --retry 10 --retry-delay 3 --retry-all-errors http://host.docker.internal:${APP_PORT}/health
                    curl -fsS -X POST http://host.docker.internal:${APP_PORT}/predict \
                      -H 'Content-Type: application/json' \
                      -d '{"review": "This product is amazing! I love it."}' | grep -q positive
                """
            }
        }
    }
     post {
        success {
            script { notifyDiscord(':white_check_mark: BUILD RIUSCITA') }
        }
        failure {
            script { notifyDiscord(':x: BUILD FALLITA') }
        }
        cleanup {
            sh 'docker image prune -f || true'
        }
    }
}