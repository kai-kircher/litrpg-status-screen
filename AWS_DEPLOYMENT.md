# AWS Deployment Guide

This guide provides step-by-step instructions for deploying the Wandering Inn Tracker to AWS.

## Option 1: Single EC2 Instance (Recommended for Starting)

**Cost:** ~$15-20/month
**Complexity:** Low
**Best for:** Development, low traffic, cost-conscious deployments

### Prerequisites

1. AWS Account
2. AWS CLI installed and configured
3. SSH key pair created in AWS EC2

### Step 1: Launch EC2 Instance

1. **Go to EC2 Dashboard** in AWS Console
2. **Launch Instance** with these settings:
   - **AMI**: Ubuntu Server 22.04 LTS (Free Tier eligible)
   - **Instance Type**: t3.small (or t4g.small for ARM, 20% cheaper)
   - **Key Pair**: Select or create your SSH key
   - **Security Group**: Create with these rules:
     - SSH (22) from your IP
     - HTTP (80) from anywhere (0.0.0.0/0)
     - HTTPS (443) from anywhere (0.0.0.0/0)
     - PostgreSQL (5432) - Optional, only if accessing DB externally
   - **Storage**: 20 GB gp3 (cheaper than gp2)

3. **Allocate Elastic IP** (optional but recommended):
   - Go to Elastic IPs → Allocate
   - Associate with your instance

### Step 2: Connect to Instance

```bash
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

### Step 3: Install Docker

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt-get install docker-compose-plugin -y

# Log out and back in for group changes to take effect
exit
```

Reconnect to the instance after logging out.

### Step 4: Clone Repository

```bash
# Install git if needed
sudo apt-get install git -y

# Clone your repository
git clone https://github.com/YOUR_USERNAME/wandering-inn-tracker.git
cd wandering-inn-tracker
```

### Step 5: Configure Environment

```bash
# Create production environment file
cat > .env.production <<EOF
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=wandering_inn_tracker
DB_USER=wandering_inn
DB_PASSWORD=$(openssl rand -base64 32)

# Node
NODE_ENV=production

# Optional: Set a custom port (default is 3000)
# PORT=3000
EOF

# Set proper permissions
chmod 600 .env.production
```

### Step 6: Run Database Migrations

```bash
# Start just the database first
docker compose up -d postgres

# Wait for PostgreSQL to be ready
sleep 10

# Run migrations
cd database
./migrate.sh  # or ./migrate.ps1 if using Windows locally
cd ..
```

### Step 7: Start Application

```bash
# Start all services
docker compose --profile web up -d

# Check logs
docker compose logs -f web
```

### Step 8: Configure Domain (Optional)

If you have a domain name:

1. **Add A Record** pointing to your Elastic IP
2. **Install Nginx** as reverse proxy:

```bash
sudo apt-get install nginx -y

# Create Nginx config
sudo nano /etc/nginx/sites-available/wandering-inn
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/wandering-inn /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

3. **Install SSL with Let's Encrypt**:

```bash
sudo apt-get install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### Step 9: Set Up Auto-Restart

```bash
# Edit docker-compose.yml to add restart policies
# (Already configured in the existing docker-compose.yml)

# Ensure Docker starts on boot
sudo systemctl enable docker
```

### Maintenance Commands

```bash
# View logs
docker compose logs -f web

# Restart services
docker compose --profile web restart

# Update application
git pull
docker compose --profile web build
docker compose --profile web up -d

# Backup database
docker exec wandering-inn-db pg_dump -U wandering_inn wandering_inn_tracker > backup_$(date +%Y%m%d).sql

# Restore database
cat backup_20250101.sql | docker exec -i wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker
```

---

## Option 2: ECS + RDS (Production-Ready)

**Cost:** ~$50-80/month
**Complexity:** Medium
**Best for:** Production, higher traffic, managed services

### Architecture

- **RDS PostgreSQL** (t4g.micro) - Managed database
- **ECS Fargate** - Containerized web app
- **Application Load Balancer** - HTTPS/SSL termination
- **Route 53** - DNS management
- **ECR** - Container image registry

### Prerequisites

1. AWS Account
2. AWS CLI configured
3. Docker installed locally
4. Domain name (optional but recommended)

### Step 1: Create RDS Database

```bash
# Create RDS PostgreSQL instance
aws rds create-db-instance \
  --db-instance-identifier wandering-inn-db \
  --db-instance-class db.t4g.micro \
  --engine postgres \
  --engine-version 16.1 \
  --master-username wandering_inn \
  --master-user-password YOUR_SECURE_PASSWORD \
  --allocated-storage 20 \
  --storage-type gp3 \
  --db-name wandering_inn_tracker \
  --backup-retention-period 7 \
  --no-publicly-accessible \
  --vpc-security-group-ids sg-YOUR_SECURITY_GROUP
```

### Step 2: Create ECR Repository

```bash
# Create repository
aws ecr create-repository \
  --repository-name wandering-inn-tracker \
  --region us-east-1

# Get login token
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
```

### Step 3: Build and Push Docker Image

```bash
# Build image
cd web
docker build -t wandering-inn-tracker:latest .

# Tag image
docker tag wandering-inn-tracker:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/wandering-inn-tracker:latest

# Push image
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/wandering-inn-tracker:latest
```

### Step 4: Create ECS Cluster

```bash
# Create cluster
aws ecs create-cluster \
  --cluster-name wandering-inn-cluster \
  --region us-east-1
```

### Step 5: Create Task Definition

Create `ecs-task-definition.json`:

```json
{
  "family": "wandering-inn-web",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "web",
      "image": "YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/wandering-inn-tracker:latest",
      "portMappings": [
        {
          "containerPort": 3000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "NODE_ENV",
          "value": "production"
        },
        {
          "name": "DB_HOST",
          "value": "YOUR_RDS_ENDPOINT"
        },
        {
          "name": "DB_PORT",
          "value": "5432"
        },
        {
          "name": "DB_NAME",
          "value": "wandering_inn_tracker"
        },
        {
          "name": "DB_USER",
          "value": "wandering_inn"
        }
      ],
      "secrets": [
        {
          "name": "DB_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:wandering-inn-db-password"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/wandering-inn-web",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "web"
        }
      }
    }
  ]
}
```

Register task definition:

```bash
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json
```

### Step 6: Create Application Load Balancer

1. Create ALB in AWS Console
2. Configure target group (port 3000)
3. Add listeners (HTTP:80, HTTPS:443)
4. Configure SSL certificate (ACM)

### Step 7: Create ECS Service

```bash
aws ecs create-service \
  --cluster wandering-inn-cluster \
  --service-name wandering-inn-web \
  --task-definition wandering-inn-web:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=web,containerPort=3000"
```

### Cost Optimization Tips

1. **Use AWS Free Tier** (first 12 months):
   - 750 hours/month t2.micro/t3.micro EC2
   - 750 hours/month RDS db.t2.micro
   - 50 GB storage

2. **Use ARM instances** (t4g family) - 20% cheaper
3. **Use gp3 storage** instead of gp2 - same cost, better performance
4. **Enable RDS storage autoscaling** - pay only for what you use
5. **Use Fargate Spot** for scraper tasks - 70% cheaper
6. **Set up CloudWatch alarms** for cost monitoring
7. **Use Reserved Instances** for long-term (1-3 year commitment)

### Monitoring

Set up CloudWatch alarms for:
- High CPU usage
- High memory usage
- Database connections
- Application errors
- Estimated charges

---

## Security Checklist

- [ ] Change default database passwords
- [ ] Enable HTTPS/SSL
- [ ] Restrict security group rules
- [ ] Enable AWS CloudTrail
- [ ] Set up AWS WAF (optional)
- [ ] Enable RDS encryption at rest
- [ ] Regular database backups
- [ ] Update dependencies regularly
- [ ] Monitor CloudWatch logs

## Accessing Admin Panel

The admin panel is only accessible via direct URL for security:

```
https://your-domain.com/admin
```

Consider adding basic auth or IP whitelist if needed.
