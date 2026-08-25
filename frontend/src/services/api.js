import axios from 'axios';

const API = axios.create({
  baseURL: '/api',
});

// Attach JWT token automatically
API.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Authentication
export const loginUser = (credentials) => API.post('/auth/login', credentials);
export const registerUser = (userData) => API.post('/auth/register', userData);
export const getMe = () => API.get('/auth/me');

// Doctors & Admin
export const fetchDoctors = () => API.get('/admin/doctors');
export const createDoctor = (docData) => API.post('/admin/doctors', docData);
export const updateDoctor = (id, docData) => API.put(`/admin/doctors/${id}`, docData);
export const addDoctorLeave = (leaveData) => API.post('/admin/leaves', leaveData);

// Appointments & Booking
export const fetchDoctorSlots = (doctorId, dateStr) => 
  API.get(`/appointments/slots?doctor_id=${doctorId}&date_str=${dateStr}`);
export const holdAppointmentSlot = (holdData) => API.post('/appointments/hold', holdData);
export const confirmAppointmentHold = (id, confirmData) => API.post(`/appointments/${id}/confirm`, confirmData);
export const rescheduleAppointment = (id, reschedData) => API.post(`/appointments/${id}/reschedule`, reschedData);
export const cancelAppointment = (id) => API.post(`/appointments/${id}/cancel`);
export const fetchAppointments = () => API.get('/appointments');

// Clinical
export const completeClinicalAppointment = (id, clinicalData) => API.post(`/clinical/appointments/${id}/complete`, clinicalData);

// Google OAuth
export const getGoogleLoginUrl = () => API.get('/auth/google/login');
export const getGoogleStatus = () => API.get('/auth/google/status');
export const disconnectGoogle = () => API.delete('/auth/google/disconnect');

export default API;
