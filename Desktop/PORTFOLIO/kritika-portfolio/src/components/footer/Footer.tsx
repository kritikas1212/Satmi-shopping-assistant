'use client';

import { motion } from 'framer-motion';
import { Github, Linkedin, Mail, ArrowUp } from 'lucide-react';

const quickLinks = [
  { name: 'About', href: '#about' },
  { name: 'Projects', href: '#projects' },
  { name: 'Blog', href: '#blog' },
  { name: 'Contact', href: '#contact' },
  { name: 'Resume', href: '/resume.pdf' },
];

export default function Footer() {
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleNavClick = (href: string) => {
    if (href.startsWith('#')) {
      const element = document.querySelector(href);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  };

  return (
    <footer className="bg-slate-900 border-t border-slate-800">
      <div className="max-w-7xl mx-auto px-6 md:px-12 lg:px-24 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
          {/* Logo & Tagline */}
          <div>
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-emerald-500 rounded-lg flex items-center justify-center font-bold text-white text-xl">
                KS
              </div>
              <span className="font-bold text-xl text-slate-100">Kritika Singh</span>
            </div>
            <p className="text-slate-400 text-sm">
              Full-Stack Developer | Shopify Specialist | ML Engineer
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="text-lg font-semibold text-slate-100 mb-4">Quick Links</h3>
            <ul className="space-y-2">
              {quickLinks.map((link) => (
                <li key={link.name}>
                  <a
                    href={link.href}
                    onClick={(e) => {
                      e.preventDefault();
                      handleNavClick(link.href);
                    }}
                    className="text-slate-400 hover:text-blue-400 transition-colors text-sm"
                    suppressHydrationWarning
                  >
                    {link.name}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Social Links */}
          <div>
            <h3 className="text-lg font-semibold text-slate-100 mb-4">Connect</h3>
            <div className="flex gap-4">
              {[
                { icon: Github, href: 'https://github.com/Kritikas1212', label: 'GitHub' },
                { icon: Linkedin, href: '#', label: 'LinkedIn' },
                { icon: Mail, href: 'mailto:kritikaasinghhh@gmail.com', label: 'Email' },
              ].map(({ icon: Icon, href, label }) => (
                <a
                  key={label}
                  href={href}
                  target={href.startsWith('http') ? '_blank' : undefined}
                  rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  className="w-10 h-10 bg-slate-800 border border-slate-700 rounded-lg flex items-center justify-center hover:border-blue-500 hover:bg-blue-500/10 transition-all group"
                  title={label}
                  suppressHydrationWarning
                >
                  <Icon className="w-5 h-5 text-slate-400 group-hover:text-blue-400 transition-colors" />
                </a>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-slate-800 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-slate-400 text-sm text-center md:text-left">
            © 2025 Kritika Singh. All rights reserved.
          </p>
          <p className="text-slate-500 text-sm text-center md:text-right">
            Built with Next.js, TypeScript, and Tailwind CSS
          </p>
        </div>
      </div>

      {/* Back to Top Button */}
      <motion.button
        onClick={scrollToTop}
        className="fixed bottom-8 right-8 w-12 h-12 bg-blue-500 hover:bg-blue-600 text-white rounded-full shadow-lg shadow-blue-500/50 flex items-center justify-center z-40"
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1 }}
      >
        <ArrowUp size={20} />
      </motion.button>
    </footer>
  );
}

