'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useInView } from 'react-intersection-observer';
import { Mail, MapPin, Github, Linkedin, Send, CheckCircle, XCircle, ArrowRight } from 'lucide-react';

const subjects = [
  'General Inquiry',
  'Job Opportunity',
  'Project Collaboration',
  'Shopify Development',
  'ML/AI Projects',
  'Other',
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: {
    opacity: 1,
    y: 0,
  },
};

export default function Contact() {
  const { ref, inView } = useInView({ threshold: 0.1, triggerOnce: true });
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: '',
    message: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'success' | 'error'>('idle');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitStatus('idle');

    try {
      // Formspree endpoint - Replace with your Formspree form ID
      // Get your form ID from https://formspree.io/forms
      const formspreeEndpoint = process.env.NEXT_PUBLIC_FORMSPREE_ENDPOINT || 'https://formspree.io/f/YOUR_FORM_ID';
      
      const response = await fetch(formspreeEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          name: formData.name,
          email: formData.email,
          subject: formData.subject,
          message: formData.message,
          _replyto: formData.email,
        }),
      });

      if (response.ok) {
        setSubmitStatus('success');
        setFormData({ name: '', email: '', subject: '', message: '' });
        setTimeout(() => setSubmitStatus('idle'), 5000);
      } else {
        throw new Error('Form submission failed');
      }
    } catch (error) {
      console.error('Form submission error:', error);
      setSubmitStatus('error');
      setTimeout(() => setSubmitStatus('idle'), 5000);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section id="contact" className="relative py-20 md:py-32 bg-slate-800/50">
      <div className="max-w-screen-2xl mx-auto px-6 md:px-8 lg:px-16 xl:px-24">
        <motion.div
          ref={ref}
          initial="hidden"
          animate={inView ? 'visible' : 'hidden'}
          variants={containerVariants}
          className="space-y-16 md:space-y-20"
        >
          {/* Section Header */}
          <motion.div variants={itemVariants} className="text-center">
            <h2 className="text-5xl md:text-6xl font-bold text-slate-100 mb-16 md:mb-20">
              <span className="text-slate-300">Get In </span>
              <span className="text-cyan-400">Touch</span>
            </h2>
            <motion.div
              className="w-32 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 mx-auto rounded-full"
              initial={{ width: 0 }}
              animate={inView ? { width: 128 } : {}}
              transition={{ delay: 0.3, duration: 0.8 }}
            />
          </motion.div>

          {/* Two Column Layout */}
          <div className="grid md:grid-cols-2 gap-16">
            {/* Left Column - Contact Form */}
            <motion.div
              variants={itemVariants}
            >
              <form onSubmit={handleSubmit} className="space-y-8">
                {/* Name */}
                <div>
                  <label htmlFor="name" className="block text-base font-medium text-slate-300 mb-3">
                    Name <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    required
                    value={formData.name}
                    onChange={handleChange}
                    className="w-full px-6 py-4 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-base focus:outline-none focus:border-cyan-500 transition-colors backdrop-blur-sm"
                    placeholder="Your Name"
                  />
                </div>

                {/* Email */}
                <div>
                  <label htmlFor="email" className="block text-base font-medium text-slate-300 mb-3">
                    Email <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    required
                    value={formData.email}
                    onChange={handleChange}
                    className="w-full px-6 py-4 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-base focus:outline-none focus:border-cyan-500 transition-colors backdrop-blur-sm"
                    placeholder="your.email@example.com"
                  />
                </div>

                {/* Subject */}
                <div>
                  <label htmlFor="subject" className="block text-base font-medium text-slate-300 mb-3">
                    Subject <span className="text-red-400">*</span>
                  </label>
                  <select
                    id="subject"
                    name="subject"
                    required
                    value={formData.subject}
                    onChange={handleChange}
                    className="w-full px-6 py-4 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-base focus:outline-none focus:border-cyan-500 transition-colors backdrop-blur-sm"
                  >
                    <option value="">Select a subject</option>
                    {subjects.map((subject) => (
                      <option key={subject} value={subject}>
                        {subject}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Message */}
                <div>
                  <label htmlFor="message" className="block text-base font-medium text-slate-300 mb-3">
                    Message <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    id="message"
                    name="message"
                    required
                    rows={8}
                    value={formData.message}
                    onChange={handleChange}
                    className="w-full px-6 py-4 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-base focus:outline-none focus:border-cyan-500 transition-colors resize-none leading-relaxed"
                    placeholder="Your message..."
                  />
                </div>

                {/* Submit Button - MUCH LARGER */}
                <motion.button
                  type="submit"
                  disabled={isSubmitting}
                  className="group relative w-full inline-flex items-center justify-center gap-4 bg-transparent border-2 border-cyan-500 text-cyan-400 px-12 py-6 rounded-lg text-xl font-semibold transition-all duration-300 hover:bg-cyan-500/10 hover:shadow-lg hover:shadow-cyan-500/50 hover:-translate-y-1 disabled:opacity-50 disabled:cursor-not-allowed overflow-hidden"
                  whileHover={{ scale: isSubmitting ? 1 : 1.02 }}
                  whileTap={{ scale: isSubmitting ? 1 : 0.98 }}
                >
                  {isSubmitting ? (
                    <>
                      <div className="w-6 h-6 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                      <span>Sending...</span>
                    </>
                  ) : (
                    <>
                      <Send size={24} />
                      <span>Send Message</span>
                      <ArrowRight className="w-6 h-6 group-hover:translate-x-1 transition-transform" />
                    </>
                  )}
                  <motion.div
                    className="absolute inset-0 bg-cyan-500/5 rounded-lg opacity-0 group-hover:opacity-100"
                    initial={false}
                  />
                </motion.button>

                {/* Status Messages */}
                <AnimatePresence>
                  {submitStatus === 'success' && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="flex items-center gap-3 p-5 bg-emerald-500/20 border border-emerald-500/30 rounded-lg text-emerald-400"
                    >
                      <CheckCircle size={22} />
                      <span className="text-base">Message sent successfully! I&apos;ll get back to you soon.</span>
                    </motion.div>
                  )}
                  {submitStatus === 'error' && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="flex items-center gap-3 p-5 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400"
                    >
                      <XCircle size={22} />
                      <span className="text-base">Something went wrong. Please try again.</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </form>
            </motion.div>

            {/* Right Column - Contact Info */}
            <motion.div
              variants={itemVariants}
              className="space-y-10"
            >
              <div>
                <h3 className="text-3xl md:text-4xl font-bold text-slate-100 mb-8">Contact Information</h3>
                <p className="text-slate-400 text-xl md:text-2xl leading-relaxed mb-12">
                  I&apos;m always open to discussing new projects, creative ideas, or opportunities to be part of your visions.
                </p>
              </div>

              {/* Contact Details */}
              <div className="space-y-6">
                <a
                  href="mailto:kritikaasinghhh@gmail.com"
                  className="flex items-center gap-5 p-6 bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl hover:border-cyan-500/50 transition-all group"
                  suppressHydrationWarning
                >
                  <div className="w-14 h-14 bg-cyan-500/20 border border-cyan-500/30 rounded-lg flex items-center justify-center group-hover:bg-cyan-500/30 transition-colors">
                    <Mail className="w-7 h-7 text-cyan-400" />
                  </div>
                  <div>
                    <div className="text-sm text-slate-400 mb-1">Email</div>
                    <div className="text-slate-100 font-medium text-base">kritikaasinghhh@gmail.com</div>
                  </div>
                </a>

                <div className="flex items-center gap-5 p-6 bg-slate-800/50 border border-slate-700 rounded-xl">
                  <div className="w-14 h-14 bg-emerald-500/20 border border-emerald-500/30 rounded-lg flex items-center justify-center">
                    <MapPin className="w-7 h-7 text-emerald-400" />
                  </div>
                  <div>
                    <div className="text-sm text-slate-400 mb-1">Location</div>
                    <div className="text-slate-100 font-medium text-base">Greater Noida, India 📍</div>
                  </div>
                </div>
              </div>

              {/* Social Links */}
              <div>
                <h4 className="text-2xl md:text-3xl font-semibold text-slate-100 mb-8">Connect With Me</h4>
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
                      className="w-16 h-16 bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl flex items-center justify-center hover:border-cyan-500 hover:bg-cyan-500/10 transition-all group"
                      title={label}
                      suppressHydrationWarning
                    >
                      <Icon className="w-7 h-7 text-slate-400 group-hover:text-cyan-400 transition-colors" />
                    </a>
                  ))}
                </div>
              </div>

              {/* Availability Status */}
              <div className="p-8 bg-emerald-500/10 border border-emerald-500/30 rounded-xl">
                <div className="flex items-center gap-3 mb-3">
                  <span className="w-3 h-3 bg-emerald-500 rounded-full animate-pulse"></span>
                  <span className="text-emerald-400 font-semibold text-base">Currently available for opportunities</span>
                </div>
                <p className="text-slate-400 text-base">I typically respond within 24 hours</p>
              </div>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
