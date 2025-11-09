# Kritika Singh - Portfolio Website

A world-class, fully responsive developer portfolio website built with Next.js 14, TypeScript, Tailwind CSS, and Framer Motion.

## 🚀 Features

- **Fully Responsive Design** - Optimized for mobile, tablet, and desktop
- **Smooth Animations** - Powered by Framer Motion for engaging interactions
- **Dark Theme** - Modern dark color palette with gradient accents
- **Performance Optimized** - Fast loading times and smooth scrolling
- **SEO Friendly** - Proper meta tags and semantic HTML
- **Accessible** - WCAG compliant with proper ARIA labels

## 🛠️ Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Animations**: Framer Motion
- **Icons**: Lucide React
- **Scroll Detection**: React Intersection Observer

## 📦 Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## 🎨 Sections

1. **Navigation** - Sticky header with smooth scroll navigation
2. **Hero** - Animated introduction with typing effect
3. **About** - Personal introduction and tech stack
4. **Experience** - Timeline of work experience
5. **Education** - Dual degree information
6. **Projects** - Featured projects with expandable details
7. **Skills** - Animated proficiency bars
8. **Achievements** - Key milestones and accomplishments
9. **Blog** - Placeholder for blog articles
10. **Contact** - Contact form and information
11. **Footer** - Quick links and social media

## 🎯 Customization

### Colors

Edit `src/app/globals.css` to customize the color palette:

```css
:root {
  --primary-bg: #0F172A;
  --secondary-bg: #1E293B;
  --accent-primary: #3B82F6;
  --accent-secondary: #10B981;
  --text-primary: #F1F5F9;
  --text-secondary: #94A3B8;
}
```

### Content

Update component files in `src/components/` to modify content:
- Personal information
- Projects
- Skills
- Experience
- Contact details

## 📝 Form Submission

The contact form is integrated with Formspree. To set it up:

1. Sign up for a free account at [Formspree](https://formspree.io/)
2. Create a new form to get your form endpoint URL (e.g., `https://formspree.io/f/xjvqkzpn`)
3. Create a `.env.local` file in the root directory:
   ```env
   NEXT_PUBLIC_FORMSPREE_ENDPOINT=https://formspree.io/f/YOUR_FORM_ID
   ```
4. Replace `YOUR_FORM_ID` with your actual Formspree form ID
5. Restart your development server

The form will automatically send submissions to your email address configured in Formspree.

## 🚀 Deployment

### Vercel (Recommended)

1. Push your code to GitHub
2. Import your repository in Vercel
3. Deploy automatically

### Other Platforms

The app can be deployed to any platform that supports Next.js:
- Netlify
- AWS Amplify
- Railway
- DigitalOcean App Platform

## 📄 License

This project is private and proprietary.

## 👤 Author

**Kritika Singh**
- GitHub: [@Kritikas1212](https://github.com/Kritikas1212)
- Email: kritikaasinghhh@gmail.com

---

Built with ❤️ using Next.js, TypeScript, and Tailwind CSS
