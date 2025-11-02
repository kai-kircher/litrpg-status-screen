# LitRPG Status Screen

A full-stack web application for tracking character progression in *The Wandering Inn* web serial. Look up any character's classes, levels, skills, and spells at any point in the story—completely spoiler-free!

![Demo Screenshot](https://via.placeholder.com/800x400?text=Screenshot+Coming+Soon)

## 🎯 Features

- **Character Progression Tracking**: Track classes, levels, skills, and spells
- **Spoiler-Free Viewing**: Filter by chapter to avoid spoilers
- **Automated Scraping**: Python scraper extracts progression events from chapters
- **Manual Processing**: Admin panel for assigning events to characters
- **Beautiful UI**: Clean, responsive dark theme interface
- **Docker Ready**: Full containerized deployment

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Local Development

1. **Clone the repository**
```bash
git clone https://github.com/kai-kircher/litrpg-status-screen.git
cd litrpg-status-screen
```

2. **Start the database**
```bash
docker-compose up -d postgres
```

3. **Run database migrations**
```bash
cd database
./migrate.sh  # or ./migrate.ps1 on Windows
cd ..
```

4. **Start the web application**
```bash
docker-compose --profile web up -d
```

5. **Access the application**
- Main app: http://localhost:3000
- Admin panel: http://localhost:3000/admin

See [GETTING_STARTED.md](GETTING_STARTED.md) for detailed setup instructions.

## 📖 Usage

### Viewing Character Progression

1. Select a character from the dropdown
2. Optionally select a maximum chapter to avoid spoilers
3. Use the search box to filter by class, skill, or spell
4. View progression organized by chapter

### Admin Panel (Processing Events)

1. Navigate to `/admin`
2. View unassigned events scraped from chapters
3. Search or create characters
4. Assign events to characters
5. Click "Process" to convert events into progression data

See [USAGE_GUIDE.md](USAGE_GUIDE.md) for more details.

## 🏗️ Architecture

### Tech Stack

- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Backend**: Next.js API routes
- **Database**: PostgreSQL 16
- **Scraper**: Python 3, BeautifulSoup, lxml
- **Deployment**: Docker, Docker Compose

### Project Structure

```
litrpg-status-screen/
├── web/                  # Next.js web application
│   ├── app/             # Next.js app directory
│   │   ├── admin/       # Admin panel
│   │   └── api/         # API routes
│   └── lib/             # Shared utilities
├── scraper/             # Python scraping application
│   └── src/
│       ├── scrapers/    # Chapter & ToC scrapers
│       ├── parsers/     # Event pattern matching
│       └── db/          # Database operations
├── database/
│   └── migrations/      # SQL migrations
└── infrastructure/      # Docker & deployment configs
```

## 🗄️ Database Schema

The application uses a two-stage data model:

1. **Raw Events**: Scraped progression events awaiting manual assignment
2. **Processed Progression**: Assigned events converted to character progression data

Key tables:
- `chapters` - Chapter metadata and content
- `characters` - Character information
- `raw_events` - Unprocessed scraped events
- `character_classes` - Class acquisitions
- `character_levels` - Level progression
- `abilities` - Skills and spells catalog
- `character_abilities` - Character ability acquisitions

See [database/README.md](database/README.md) for full schema documentation.

## 🔧 Development

### Running the Scraper

```bash
# Build chapter list from Table of Contents
docker-compose --profile scraper run scraper python -m src.main build-toc

# Scrape chapter content
docker-compose --profile scraper run scraper python -m src.main scrape --max 10

# Test scraper on a single chapter
docker-compose --profile scraper run scraper python -m src.main test 1
```

See [SCRAPER_WORKFLOW.md](SCRAPER_WORKFLOW.md) for detailed scraping instructions.

### Database Operations

```bash
# Run migrations
cd database && ./migrate.sh

# Backup database
docker exec wandering-inn-db pg_dump -U wandering_inn wandering_inn_tracker > backup.sql

# Restore database
cat backup.sql | docker exec -i wandering-inn-db psql -U wandering_inn -d wandering_inn_tracker
```

## 🚢 Deployment

### AWS Deployment

Choose from two deployment options:

1. **Single EC2 Instance** (~$15-20/month)
   - Simple setup, all services on one instance
   - Best for development and low traffic

2. **ECS + RDS** (~$50-80/month)
   - Production-ready with managed services
   - Auto-scaling, high availability

See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) for step-by-step deployment guides.

### Production Deployment Script

```bash
# Copy and configure environment
cp .env.production.example .env.production
# Edit .env.production with secure passwords

# Deploy
./deploy.sh  # or ./deploy.ps1 on Windows
```

## 📚 Documentation

- [Getting Started Guide](GETTING_STARTED.md) - Complete setup walkthrough
- [Usage Guide](USAGE_GUIDE.md) - How to use the application
- [Docker Setup](DOCKER_SETUP.md) - Docker configuration details
- [Database Setup](DATABASE_SETUP.md) - Database schema and migrations
- [Scraper Workflow](SCRAPER_WORKFLOW.md) - Scraping chapter content
- [AWS Deployment](AWS_DEPLOYMENT.md) - Cloud deployment guide

## 🤝 Contributing

This is a personal project, but suggestions and bug reports are welcome! Please open an issue to discuss any changes.

## 📝 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- **The Wandering Inn** by pirateaba - The amazing web serial that inspired this project
- Built with guidance from **Claude Code** by Anthropic

## ⚠️ Disclaimer

This is an unofficial fan project. *The Wandering Inn* and all related content are the property of pirateaba. This tool is designed to enhance the reading experience and should not be used to replace reading the original work.

---

**Note**: The scraper respects the website's robots.txt and includes rate limiting (10-second delay between requests as specified in robots.txt) to avoid server strain.
