import React, { useState, useEffect } from 'react';
import { 
  fetchDoctors, fetchDoctorSlots, holdAppointmentSlot, 
  confirmAppointmentHold, rescheduleAppointment, cancelAppointment, fetchAppointments 
} from '../services/api';
import { 
  Search, Calendar as CalendarIcon, Clock, CheckCircle2, AlertCircle, 
  RotateCcw, XCircle, Stethoscope, Pill, FileText, Sparkles, Timer
} from 'lucide-react';

export const PatientDashboard = () => {
  const [doctors, setDoctors] = useState([]);
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [selectedSpecialization, setSelectedSpecialization] = useState('All');
  const [bookingDate, setBookingDate] = useState(new Date().toISOString().split('T')[0]);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);

  // Active Hold State
  const [heldAppointment, setHeldAppointment] = useState(null);
  const [holdTimeRemaining, setHoldTimeRemaining] = useState(0);
  const [symptoms, setSymptoms] = useState('');
  const [submittingSymptoms, setSubmittingSymptoms] = useState(false);

  // Patient Appointments
  const [myAppointments, setMyAppointments] = useState([]);
  const [loadingAppointments, setLoadingAppointments] = useState(true);

  // Modal / Action states
  const [viewingSummaryAppt, setViewingSummaryAppt] = useState(null);
  const [reschedulingAppt, setReschedulingAppt] = useState(null);
  const [rescheduleDate, setRescheduleDate] = useState('');
  const [rescheduleSlots, setRescheduleSlots] = useState([]);
  const [actionMessage, setActionMessage] = useState('');

  useEffect(() => {
    loadDoctors();
    loadMyAppointments();
  }, []);

  useEffect(() => {
    if (selectedDoctor && bookingDate) {
      loadSlots(selectedDoctor.id, bookingDate);
    }
  }, [selectedDoctor, bookingDate]);

  // Hold Timer countdown
  useEffect(() => {
    let timer;
    if (heldAppointment && holdTimeRemaining > 0) {
      timer = setInterval(() => {
        setHoldTimeRemaining((prev) => {
          if (prev <= 1) {
            setHeldAppointment(null);
            setActionMessage('Your 5-minute slot hold has expired. Please select the slot again.');
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [heldAppointment, holdTimeRemaining]);

  const loadDoctors = async () => {
    try {
      const res = await fetchDoctors();
      setDoctors(res.data);
      if (res.data.length > 0) {
        setSelectedDoctor(res.data[0]);
      }
    } catch (err) {
      console.error("Error loading doctors", err);
    }
  };

  const loadMyAppointments = async () => {
    setLoadingAppointments(true);
    try {
      const res = await fetchAppointments();
      setMyAppointments(res.data);
    } catch (err) {
      console.error("Error loading appointments", err);
    } finally {
      setLoadingAppointments(false);
    }
  };

  const loadSlots = async (doctorId, dateStr) => {
    setLoadingSlots(true);
    try {
      const res = await fetchDoctorSlots(doctorId, dateStr);
      setAvailableSlots(res.data);
    } catch (err) {
      console.error("Error loading slots", err);
      setAvailableSlots([]);
    } finally {
      setLoadingSlots(false);
    }
  };

  const handleHoldSlot = async (slot) => {
    setActionMessage('');
    try {
      const res = await holdAppointmentSlot({
        doctor_id: selectedDoctor.id,
        start_time: slot.start_time,
        end_time: slot.end_time
      });
      setHeldAppointment(res.data);
      
      // Calculate remaining seconds for 5 minute hold
      const expiresAt = new Date(res.data.hold_expires_at).getTime();
      const now = new Date().getTime();
      const diffSecs = Math.max(0, Math.floor((expiresAt - now) / 1000));
      setHoldTimeRemaining(diffSecs);
    } catch (err) {
      setActionMessage(err.response?.data?.detail || 'Failed to hold slot');
    }
  };

  const handleConfirmHold = async () => {
    if (!symptoms.trim()) {
      alert("Please describe your symptoms before confirming.");
      return;
    }
    setSubmittingSymptoms(true);
    setActionMessage('');
    try {
      await confirmAppointmentHold(heldAppointment.id, { symptoms });
      setHeldAppointment(null);
      setSymptoms('');
      setActionMessage('Appointment successfully booked and confirmed!');
      loadMyAppointments();
      if (selectedDoctor && bookingDate) {
        loadSlots(selectedDoctor.id, bookingDate);
      }
    } catch (err) {
      setActionMessage(err.response?.data?.detail || 'Failed to confirm appointment');
    } finally {
      setSubmittingSymptoms(false);
    }
  };

  const handleCancelAppointment = async (apptId) => {
    if (window.confirm("Are you sure you want to cancel this appointment?")) {
      try {
        await cancelAppointment(apptId);
        loadMyAppointments();
        if (selectedDoctor && bookingDate) {
          loadSlots(selectedDoctor.id, bookingDate);
        }
      } catch (err) {
        alert(err.response?.data?.detail || 'Cancellation failed');
      }
    }
  };

  const handleOpenReschedule = (appt) => {
    setReschedulingAppt(appt);
    setRescheduleDate(appt.start_time.split('T')[0]);
    loadRescheduleSlots(appt.doctor_id, appt.start_time.split('T')[0]);
  };

  const loadRescheduleSlots = async (docId, dateStr) => {
    try {
      const res = await fetchDoctorSlots(docId, dateStr);
      setRescheduleSlots(res.data);
    } catch (err) {
      setRescheduleSlots([]);
    }
  };

  const handleConfirmReschedule = async (newSlot) => {
    try {
      await rescheduleAppointment(reschedulingAppt.id, {
        start_time: newSlot.start_time,
        end_time: newSlot.end_time
      });
      setReschedulingAppt(null);
      setActionMessage('Appointment successfully rescheduled!');
      loadMyAppointments();
    } catch (err) {
      alert(err.response?.data?.detail || 'Reschedule failed');
    }
  };

  // Specialization filters
  const specializations = ['All', ...new Set(doctors.map(d => d.specialization))];
  const filteredDoctors = selectedSpecialization === 'All' 
    ? doctors 
    : doctors.filter(d => d.specialization === selectedSpecialization);

  const formatTime = (timeString) => {
    return new Date(timeString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatTimerMinSec = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      
      {/* Banner / Action message */}
      {actionMessage && (
        <div className="p-4 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-300 text-sm flex items-center justify-between shadow-lg">
          <span>{actionMessage}</span>
          <button onClick={() => setActionMessage('')} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* 5-MINUTE SLOT HOLD ACTIVE WIDGET */}
      {heldAppointment && (
        <div className="glass-panel p-6 rounded-2xl border-2 border-amber-500/40 glow-cyan relative overflow-hidden">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-4 pb-4 border-b border-slate-800">
            <div>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                <Timer className="w-4 h-4 animate-pulse text-amber-400" />
                Temporary Slot Hold Active
              </span>
              <h2 className="text-xl font-bold text-slate-100 mt-2">
                Complete Your Booking (Hold Expires in {formatTimerMinSec(holdTimeRemaining)})
              </h2>
              <p className="text-xs text-slate-400">
                Dr. {selectedDoctor?.first_name} {selectedDoctor?.last_name} • {formatTime(heldAppointment.start_time)} - {formatTime(heldAppointment.end_time)}
              </p>
            </div>
            
            <div className="text-right font-mono text-2xl font-extrabold text-amber-400 bg-slate-950/80 px-4 py-2 rounded-xl border border-amber-500/30">
              {formatTimerMinSec(holdTimeRemaining)}
            </div>
          </div>

          {/* Pre-Visit Symptoms Form */}
          <div className="space-y-3">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
              Enter Your Symptoms (Required for AI Pre-Visit Analysis)
            </label>
            <textarea
              rows={3}
              required
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              placeholder="e.g. Sharp pain in lower back for 3 days, mild fever..."
              className="w-full bg-slate-950/70 border border-slate-800 rounded-xl p-3 text-slate-200 text-sm focus:outline-none focus:border-amber-500 transition-all"
            ></textarea>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setHeldAppointment(null)}
                className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-medium"
              >
                Cancel Hold
              </button>
              <button
                onClick={handleConfirmHold}
                disabled={submittingSymptoms}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-emerald-500 hover:from-amber-400 hover:to-emerald-400 text-slate-950 font-bold text-xs uppercase tracking-wider flex items-center gap-2 shadow-lg shadow-amber-500/20 transition-all disabled:opacity-50"
              >
                {submittingSymptoms ? 'Processing AI & Confirming...' : 'Confirm Appointment Booking'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MAIN LAYOUT: DOCTOR SEARCH & BOOKING */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left 2 Columns: Doctors & Available Slots */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-panel p-6 rounded-2xl space-y-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                  <Stethoscope className="w-5 h-5 text-sky-400" />
                  Find a Doctor & Book Slot
                </h2>
                <p className="text-xs text-slate-400">Select specialization, doctor, and date to view working slots</p>
              </div>

              {/* Date Selector */}
              <div className="flex items-center gap-2 bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2">
                <CalendarIcon className="w-4 h-4 text-sky-400" />
                <input
                  type="date"
                  min={new Date().toISOString().split('T')[0]}
                  value={bookingDate}
                  onChange={(e) => setBookingDate(e.target.value)}
                  className="bg-transparent text-slate-200 text-xs font-semibold focus:outline-none"
                />
              </div>
            </div>

            {/* Specialization Filter Pills */}
            <div className="flex items-center gap-2 overflow-x-auto pb-2">
              {specializations.map(spec => (
                <button
                  key={spec}
                  onClick={() => setSelectedSpecialization(spec)}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                    selectedSpecialization === spec
                      ? 'bg-sky-500 text-slate-950 font-bold shadow-md shadow-sky-500/20'
                      : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {spec}
                </button>
              ))}
            </div>

            {/* Doctors Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {filteredDoctors.map(doc => (
                <div
                  key={doc.id}
                  onClick={() => setSelectedDoctor(doc)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    selectedDoctor?.id === doc.id
                      ? 'bg-sky-500/10 border-sky-500/50 glow-cyan'
                      : 'bg-slate-950/40 border-slate-800/80 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-bold text-slate-100">Dr. {doc.first_name} {doc.last_name}</h3>
                      <span className="text-xs text-sky-400 font-medium">{doc.specialization}</span>
                    </div>
                    <span className="text-[10px] font-semibold text-slate-400 bg-slate-800 px-2 py-1 rounded-md">
                      {doc.slot_duration_minutes} min slots
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Available Slots Display */}
            {selectedDoctor && (
              <div className="pt-4 border-t border-slate-800">
                <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-emerald-400" />
                  Available Slots for Dr. {selectedDoctor.last_name} on {bookingDate}
                </h3>

                {loadingSlots ? (
                  <div className="p-8 text-center text-slate-400 text-xs">Loading available slots...</div>
                ) : availableSlots.length === 0 ? (
                  <div className="p-6 text-center text-slate-400 text-xs bg-slate-950/40 rounded-xl border border-slate-800">
                    No available slots on this date. Doctor may be on leave or fully booked.
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                    {availableSlots.map((slot, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleHoldSlot(slot)}
                        className="py-2.5 px-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 text-emerald-300 text-xs font-semibold transition-all hover:scale-105"
                      >
                        {formatTime(slot.start_time)} - {formatTime(slot.end_time)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>
        </div>

        {/* Right 1 Column: My Appointments */}
        <div className="space-y-6">
          <div className="glass-panel p-6 rounded-2xl space-y-4">
            <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
              <CalendarIcon className="w-5 h-5 text-emerald-400" />
              My Appointments
            </h2>

            {loadingAppointments ? (
              <div className="text-center py-6 text-xs text-slate-400">Loading your schedule...</div>
            ) : myAppointments.length === 0 ? (
              <div className="text-center py-6 text-xs text-slate-400">No appointments scheduled</div>
            ) : (
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                {myAppointments.map(appt => (
                  <div key={appt.id} className="p-4 rounded-xl glass-card space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-bold text-slate-200 text-sm">
                          Dr. {appt.doctor?.user?.last_name || 'Doctor'}
                        </div>
                        <div className="text-xs text-slate-400">
                          {new Date(appt.start_time).toLocaleDateString()} • {formatTime(appt.start_time)}
                        </div>
                      </div>
                      
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        appt.status === 'CONFIRMED' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        appt.status === 'COMPLETED' ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' :
                        appt.status === 'CANCELLED' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                        'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                      }`}>
                        {appt.status}
                      </span>
                    </div>

                    {/* Symptoms & Urgency */}
                    {appt.symptoms && (
                      <div className="text-xs text-slate-300 bg-slate-950/40 p-2.5 rounded-lg">
                        <span className="text-slate-400 font-semibold">Symptoms:</span> {appt.symptoms}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
                      {appt.status === 'COMPLETED' ? (
                        <button
                          onClick={() => setViewingSummaryAppt(appt)}
                          className="text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1"
                        >
                          <Sparkles className="w-3.5 h-3.5" /> View AI Post-Visit Summary
                        </button>
                      ) : appt.status === 'CONFIRMED' ? (
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => handleOpenReschedule(appt)}
                            className="text-amber-400 hover:text-amber-300 font-semibold flex items-center gap-1"
                          >
                            <RotateCcw className="w-3.5 h-3.5" /> Reschedule
                          </button>
                          <button
                            onClick={() => handleCancelAppointment(appt.id)}
                            className="text-rose-400 hover:text-rose-300 font-semibold flex items-center gap-1"
                          >
                            <XCircle className="w-3.5 h-3.5" /> Cancel
                          </button>
                        </div>
                      ) : null}
                    </div>

                  </div>
                ))}
              </div>
            )}

          </div>
        </div>

      </div>

      {/* POST VISIT SUMMARY MODAL */}
      {viewingSummaryAppt && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-2xl w-full glass-panel rounded-2xl p-6 space-y-6 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-sky-400" />
                Post-Visit Summary & Medication Schedule
              </h3>
              <button onClick={() => setViewingSummaryAppt(null)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            {/* AI Explanation */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Patient Explanation</h4>
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-sm text-slate-200 whitespace-pre-line">
                {viewingSummaryAppt.ai_patient_summary}
              </div>
            </div>

            {/* Prescriptions & Medications */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Pill className="w-4 h-4 text-emerald-400" /> Medication Schedule & Reminders
              </h4>
              
              {viewingSummaryAppt.medications && viewingSummaryAppt.medications.length > 0 ? (
                <div className="space-y-2">
                  {viewingSummaryAppt.medications.map(m => (
                    <div key={m.id} className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between">
                      <div>
                        <div className="font-bold text-emerald-300 text-sm">{m.name} ({m.dosage})</div>
                        <div className="text-xs text-slate-400">Frequency: {m.frequency} • {m.start_date} to {m.end_date}</div>
                      </div>
                      
                      {m.reminder_times && m.reminder_times.length > 0 ? (
                        <span className="text-[10px] font-bold bg-emerald-500/20 text-emerald-300 px-2.5 py-1 rounded-full">
                          Reminders: {m.reminder_times.join(', ')} UTC
                        </span>
                      ) : (
                        <span className="text-[10px] font-bold bg-amber-500/20 text-amber-300 px-2.5 py-1 rounded-full">
                          Reminders Need Configuration
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-3 text-xs text-slate-400 bg-slate-950/40 rounded-xl">No medications prescribed</div>
              )}
            </div>

            {/* Follow-up steps */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Follow-Up Steps</h4>
              <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-300">
                {viewingSummaryAppt.ai_follow_up_steps}
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setViewingSummaryAppt(null)}
                className="px-5 py-2 rounded-xl bg-slate-800 text-slate-200 text-xs font-semibold hover:bg-slate-700"
              >
                Close Summary
              </button>
            </div>
          </div>
        </div>
      )}

      {/* RESCHEDULE MODAL */}
      {reschedulingAppt && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-md w-full glass-panel rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-100">Reschedule Appointment</h3>
              <button onClick={() => setReschedulingAppt(null)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Target Date</label>
              <input
                type="date"
                min={new Date().toISOString().split('T')[0]}
                value={rescheduleDate}
                onChange={(e) => {
                  setRescheduleDate(e.target.value);
                  loadRescheduleSlots(reschedulingAppt.doctor_id, e.target.value);
                }}
                className="w-full bg-slate-950/60 border border-slate-800 rounded-xl p-2.5 text-slate-200 text-sm focus:outline-none"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">Select New Slot</label>
              {rescheduleSlots.length === 0 ? (
                <div className="text-xs text-slate-400 p-4 text-center border border-slate-800 rounded-xl">No slots available on this date</div>
              ) : (
                <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                  {rescheduleSlots.map((slot, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleConfirmReschedule(slot)}
                      className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-medium hover:bg-amber-500/20"
                    >
                      {formatTime(slot.start_time)} - {formatTime(slot.end_time)}
                    </button>
                  ))}
                </div>
              )}
            </div>

          </div>
        </div>
      )}

    </div>
  );
};
