import React, { useState, useEffect } from 'react';
import { fetchAppointments, completeClinicalAppointment } from '../services/api';
import { Stethoscope, Calendar, Clock, AlertTriangle, Sparkles, CheckCircle2, Pill, Plus, Trash2, HelpCircle } from 'lucide-react';

export const DoctorDashboard = () => {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);

  // Selected appointment for clinical completion
  const [selectedAppt, setSelectedAppt] = useState(null);
  const [clinicalNotes, setClinicalNotes] = useState('');
  const [prescription, setPrescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Medication list entry
  const [medications, setMedications] = useState([
    { name: '', dosage: '', frequency: 'twice daily', reminder_times: ['08:00', '20:00'], start_date: new Date().toISOString().split('T')[0], end_date: new Date(Date.now() + 7*24*60*60*1000).toISOString().split('T')[0] }
  ]);

  useEffect(() => {
    loadAppointments();
  }, []);

  const loadAppointments = async () => {
    setLoading(true);
    try {
      const res = await fetchAppointments();
      setAppointments(res.data);
    } catch (err) {
      console.error("Error loading doctor appointments", err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenCompleteModal = (appt) => {
    setSelectedAppt(appt);
    setClinicalNotes('');
    setPrescription('');
    setMedications([
      { name: '', dosage: '', frequency: 'twice daily', reminder_times: ['08:00', '20:00'], start_date: new Date().toISOString().split('T')[0], end_date: new Date(Date.now() + 7*24*60*60*1000).toISOString().split('T')[0] }
    ]);
  };

  const handleAddMedication = () => {
    setMedications([
      ...medications,
      { name: '', dosage: '', frequency: 'once daily', reminder_times: ['09:00'], start_date: new Date().toISOString().split('T')[0], end_date: new Date(Date.now() + 7*24*60*60*1000).toISOString().split('T')[0] }
    ]);
  };

  const handleRemoveMedication = (index) => {
    setMedications(medications.filter((_, i) => i !== index));
  };

  const handleMedicationChange = (index, field, value) => {
    const updated = [...medications];
    updated[index][field] = value;
    setMedications(updated);
  };

  const handleReminderTimesChange = (index, timeStr) => {
    const updated = [...medications];
    // Split by comma if multiple
    const times = timeStr.split(',').map(t => t.trim()).filter(Boolean);
    updated[index].reminder_times = times;
    setMedications(updated);
  };

  const handleSubmitClinical = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      // Filter out empty medication names
      const validMeds = medications.filter(m => m.name.trim() !== '');

      await completeClinicalAppointment(selectedAppt.id, {
        clinical_notes: clinicalNotes,
        prescription: prescription,
        medications: validMeds
      });

      setSelectedAppt(null);
      loadAppointments();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to complete appointment');
    } finally {
      setSubmitting(false);
    }
  };

  const getUrgencyBadge = (urgency) => {
    switch (urgency) {
      case 'High':
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30"><AlertTriangle className="w-3.5 h-3.5" /> High Urgency</span>;
      case 'Medium':
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30"><AlertTriangle className="w-3.5 h-3.5" /> Medium Urgency</span>;
      default:
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"><CheckCircle2 className="w-3.5 h-3.5" /> Low Urgency</span>;
    }
  };

  const formatTime = (timeString) => {
    return new Date(timeString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      
      <div className="glass-panel p-6 rounded-2xl flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <Stethoscope className="w-6 h-6 text-emerald-400" />
            Doctor Clinical Dashboard
          </h1>
          <p className="text-sm text-slate-400 mt-1">Review patient symptoms, AI pre-visit insights, and complete appointments</p>
        </div>
      </div>

      {/* Appointments List */}
      <div className="glass-panel p-6 rounded-2xl space-y-6">
        <h2 className="text-lg font-bold text-slate-200">Patient Appointments & Pre-visit Summaries</h2>

        {loading ? (
          <div className="text-center py-12 text-slate-400 text-xs">Loading appointments...</div>
        ) : appointments.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-xs">No appointments scheduled for you</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {appointments.map(appt => (
              <div key={appt.id} className="glass-card p-5 rounded-xl space-y-4 flex flex-col justify-between">
                
                <div className="space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-bold text-slate-100 text-base">
                        {appt.patient?.first_name} {appt.patient?.last_name}
                      </h3>
                      <div className="text-xs text-slate-400 flex items-center gap-2 mt-1">
                        <Calendar className="w-3.5 h-3.5 text-sky-400" />
                        {new Date(appt.start_time).toLocaleDateString()}
                        <Clock className="w-3.5 h-3.5 text-sky-400 ml-2" />
                        {formatTime(appt.start_time)} - {formatTime(appt.end_time)}
                      </div>
                    </div>

                    <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                      appt.status === 'CONFIRMED' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                      appt.status === 'COMPLETED' ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' :
                      'bg-slate-800 text-slate-400'
                    }`}>
                      {appt.status}
                    </span>
                  </div>

                  {/* Pre-visit AI Urgency & Chief Complaint */}
                  {appt.symptoms && (
                    <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-300">Reported Symptoms:</span>
                        {getUrgencyBadge(appt.ai_urgency_level)}
                      </div>
                      <p className="text-slate-300 italic">{appt.symptoms}</p>
                      
                      {appt.ai_chief_complaint && (
                        <div className="pt-2 border-t border-slate-800">
                          <span className="text-sky-400 font-semibold">AI Chief Complaint:</span> {appt.ai_chief_complaint}
                        </div>
                      )}
                    </div>
                  )}

                  {/* AI Suggested Questions for Doctor */}
                  {appt.ai_suggested_questions && appt.ai_suggested_questions.length > 0 && (
                    <div className="p-3.5 rounded-xl bg-sky-500/10 border border-sky-500/20 text-xs space-y-1.5">
                      <span className="font-bold text-sky-300 flex items-center gap-1.5">
                        <HelpCircle className="w-4 h-4 text-sky-400" /> AI Suggested Consultation Questions:
                      </span>
                      <ul className="list-disc list-inside text-slate-300 space-y-1 pl-1">
                        {appt.ai_suggested_questions.map((q, idx) => (
                          <li key={idx}>{q}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="pt-3 border-t border-slate-800 flex justify-end">
                  {appt.status === 'CONFIRMED' ? (
                    <button
                      onClick={() => handleOpenCompleteModal(appt)}
                      className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-sky-500 hover:from-emerald-400 hover:to-sky-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20"
                    >
                      <Sparkles className="w-4 h-4" /> Enter Notes & Generate AI Summary
                    </button>
                  ) : (
                    <span className="text-xs text-slate-500 font-medium">Appointment Completed</span>
                  )}
                </div>

              </div>
            ))}
          </div>
        )}
      </div>

      {/* CLINICAL COMPLETION MODAL */}
      {selectedAppt && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-3xl w-full glass-panel rounded-2xl p-6 space-y-6 max-h-[90vh] overflow-y-auto">
            
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-100">
                  Complete Appointment for {selectedAppt.patient?.first_name} {selectedAppt.patient?.last_name}
                </h3>
                <p className="text-xs text-slate-400">Enter clinical diagnosis notes, prescriptions, and custom reminder times</p>
              </div>
              <button onClick={() => setSelectedAppt(null)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <form onSubmit={handleSubmitClinical} className="space-y-5">
              
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Clinical Diagnosis Notes
                </label>
                <textarea
                  rows={3}
                  required
                  value={clinicalNotes}
                  onChange={(e) => setClinicalNotes(e.target.value)}
                  placeholder="Enter detailed examination findings and clinical notes..."
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-xl p-3 text-slate-200 text-sm focus:outline-none focus:border-sky-500"
                ></textarea>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Prescription Details
                </label>
                <textarea
                  rows={2}
                  required
                  value={prescription}
                  onChange={(e) => setPrescription(e.target.value)}
                  placeholder="e.g. Amoxicillin 500mg, Take 1 tablet twice daily after meals for 7 days"
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-xl p-3 text-slate-200 text-sm focus:outline-none focus:border-sky-500"
                ></textarea>
              </div>

              {/* Medication Builder */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
                    <Pill className="w-4 h-4" /> Prescribed Medications & Custom Reminder Times
                  </span>
                  <button
                    type="button"
                    onClick={handleAddMedication}
                    className="px-3 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs font-semibold flex items-center gap-1"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Medication
                  </button>
                </div>

                {medications.map((med, idx) => (
                  <div key={idx} className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1">Medication Name</label>
                        <input
                          type="text"
                          required
                          value={med.name}
                          onChange={(e) => handleMedicationChange(idx, 'name', e.target.value)}
                          placeholder="Amoxicillin"
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1">Dosage</label>
                        <input
                          type="text"
                          required
                          value={med.dosage}
                          onChange={(e) => handleMedicationChange(idx, 'dosage', e.target.value)}
                          placeholder="500mg"
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1">Frequency</label>
                        <input
                          type="text"
                          required
                          value={med.frequency}
                          onChange={(e) => handleMedicationChange(idx, 'frequency', e.target.value)}
                          placeholder="twice daily"
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1">Start Date</label>
                        <input
                          type="date"
                          required
                          value={med.start_date}
                          onChange={(e) => handleMedicationChange(idx, 'start_date', e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1">End Date</label>
                        <input
                          type="date"
                          required
                          value={med.end_date}
                          onChange={(e) => handleMedicationChange(idx, 'end_date', e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-200"
                        />
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase font-bold text-amber-400 mb-1">Reminder Times (HH:MM UTC, comma separated)</label>
                        <input
                          type="text"
                          value={med.reminder_times ? med.reminder_times.join(', ') : ''}
                          onChange={(e) => handleReminderTimesChange(idx, e.target.value)}
                          placeholder="08:00, 20:00"
                          className="w-full bg-slate-900 border border-amber-500/30 rounded-lg p-2 text-xs text-amber-300 font-mono"
                        />
                      </div>
                    </div>

                    {medications.length > 1 && (
                      <div className="flex justify-end pt-1">
                        <button
                          type="button"
                          onClick={() => handleRemoveMedication(idx)}
                          className="text-rose-400 hover:text-rose-300 text-xs font-semibold flex items-center gap-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" /> Remove Medication
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setSelectedAppt(null)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-sky-500 hover:from-emerald-400 hover:to-sky-400 text-slate-950 font-bold text-xs uppercase tracking-wider flex items-center gap-2 shadow-lg shadow-emerald-500/20 transition-all disabled:opacity-50"
                >
                  {submitting ? 'Generating AI Summary...' : 'Complete Appointment'}
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

    </div>
  );
};
