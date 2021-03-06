
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp
import argparse as arg

from polimi.switching import Boost, solve_ivp_switch
from polimi.envelope import BEEnvelope, TrapEnvelope
from polimi.shooting import EnvelopeShooting

# for saving data
pack = lambda t,y: np.concatenate((np.reshape(t,(len(t),1)),y.transpose()),axis=1)

progname = os.path.basename(sys.argv[0])

def system(use_ramp):
    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5

    def Vref_fun(t):
        n_period = int(t / T)
        if n_period > 50 and n_period < 75:
            return Vref*0.8
        return Vref

    t0 = 0
    t_end = 50*T
    t_span = np.array([t0, t_end])

    y0 = np.array([Vin,1])

    fun_rtol = 1e-10
    fun_atol = 1e-12

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, clock_phase=0, use_compensating_ramp=use_ramp)

    print('Vector field index at the beginning of the first integration: %d.' % boost.vector_field_index)
    sol_a = solve_ivp_switch(boost, t_span, y0, \
                             method='BDF', jac=boost.jac, \
                             rtol=fun_rtol, atol=fun_atol)
    print('Vector field index at the end of the first integration: %d.' % boost.vector_field_index)

    print('Vector field index at the beginning of the second integration: %d.' % boost.vector_field_index)
    sol_b = solve_ivp_switch(boost, sol_a['t'][-1]+t_span, sol_a['y'][:,-1], \
                             method='BDF', jac=boost.jac, \
                             rtol=fun_rtol, atol=fun_atol)
    print('Vector field index at the end of the second integration: %d.' % boost.vector_field_index)

    show_manifold = True
    if show_manifold:
        n_rows = 3
    else:
        n_rows = 2

    fig,ax = plt.subplots(n_rows, 1, sharex=True, figsize=(6,4))
    ax[0].plot([0, sol_b['t'][-1]*1e6], [Vin,Vin], 'b')
    ax[0].plot(sol_a['t']*1e6, sol_a['y'][0], 'k', lw=1)
    ax[0].plot(sol_b['t']*1e6, sol_b['y'][0], 'r', lw=1)
    ax[0].set_ylabel(r'$V_C$ (V)')
    ax[1].plot(sol_a['t']*1e6, sol_a['y'][1], 'k', lw=1)
    ax[1].plot(sol_b['t']*1e6, sol_b['y'][1], 'r', lw=1)
    ax[1].set_ylabel(r'$I_L$ (A)')
    ax[1].set_xlim(t_span*2*1e6)
    if show_manifold:
        iL = sol_a['y'][1]
        t = sol_a['t']
        n = len(t)
        ramp = np.zeros(n)
        k = 0
        for i in range(n):
            if t[i] >= (k+1)*T:
                k += 1
            ramp[i] = (t[i] - k*T) / T
        ax[2].plot(sol_a['t']*1e6, - Vref + ki*iL, 'c--', lw=1, label=r'$k_i I_L - V_{ref}$')
        ax[2].plot(sol_a['t']*1e6, Vref - ki*iL, 'g', lw=1, label=r'$V_{ref} - k_i I_L$')
        ax[2].plot(sol_a['t']*1e6, ramp, 'm', lw=1, label=r'$V_{ramp}$')
        ax[2].plot(sol_a['t']*1e6, ramp - (Vref - ki*iL), 'y', lw=1, label='Manifold')
        ax[2].plot([0, sol_a['t'][-1]*1e6], [0,0], 'b')
        ax[2].set_xlabel(r'Time ($\mu$s)')
        ax[2].legend(loc='best')
    else:
        ax[1].set_xlabel(r'Time ($\mu$s)')
    plt.show()


def system_var_R(use_ramp):
    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5
    C0 = 47e-6
    L0 = 10e-6
    R0 = 5

    t0 = 0
    t_end = 200*T
    t_span = np.array([t0, t_end])

    #y0 = np.array([9.3124, 1.2804])
    y0 = np.array([10.154335434351671, 1.623030961224813])

    fun_rtol = 1e-12
    fun_atol = 1e-14

    def R_fun_square(t):
        n_period = int(t / T)
        if n_period % 100 < 75:
            return R0
        return 2*R0

    def R_fun_sin(t):
        F = 500 # [Hz]
        dR0 = R0/10
        return R0 - dR0/2 + dR0*np.sin(2*np.pi*F*t)

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, C=C0*30, L=L0*2, \
                  R=R_fun_square, use_compensating_ramp=use_ramp)

    print('Vector field index at the beginning of the integration: %d.' % boost.vector_field_index)
    sol = solve_ivp_switch(boost, t_span, y0, \
                           method='BDF', jac=boost.jac, \
                           rtol=fun_rtol, atol=fun_atol)
    print('Vector field index at the end of the integration: %d.' % boost.vector_field_index)

    fig,(ax1,ax2) = plt.subplots(2, 1, sharex=True)
    ax1.plot(sol['t']*1e6, sol['y'][0], 'k', lw=1)
    ax1.set_ylabel(r'$V_C$ (V)')
    ax2.plot(sol['t']*1e6, sol['y'][1], 'k', lw=1)
    ax2.set_xlabel(r'Time ($\mu$s)')
    ax2.set_ylabel(r'$I_L$ (A)')
    ax2.set_xlim(t_span*1e6)
    plt.show()


def envelope(use_ramp):
    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, clock_phase=0, use_compensating_ramp=use_ramp)

    fun_rtol = 1e-10
    fun_atol = 1e-12

    y0 = np.array([Vin,0])
    t_span = np.array([0, 500*T])

    t_tran = 0.*T
    if t_tran > 0:
        sol = solve_ivp_switch(boost, [0,t_tran], y0, \
                               method='BDF', jac=boost.jac, \
                               rtol=fun_rtol, atol=fun_atol)
        #plt.plot(sol['t']*1e6,sol['y'][0],'k')
        #plt.plot(sol['t']*1e6,sol['y'][1],'r')
        #plt.show()
        t_span += sol['t'][-1]
        y0 = sol['y'][:,-1]

    print('t_span =', t_span)
    print('y0 =', y0)
    print('index =', boost.vector_field_index)

    print('-' * 81)
    be_solver = BEEnvelope(boost, t_span, y0, max_step=1000, \
                           T_guess=None, T=T, \
                           env_rtol=1e-2, env_atol=1e-3, \
                           solver=solve_ivp_switch, \
                           jac=boost.jac, method='BDF', \
                           rtol=fun_rtol, atol=fun_atol)
    sol_be = be_solver.solve()
    print('-' * 81)
    trap_solver = TrapEnvelope(boost, t_span, y0, max_step=1000, \
                               T_guess=None, T=T, \
                               env_rtol=1e-2, env_atol=1e-3, \
                               solver=solve_ivp_switch, \
                               jac=boost.jac, method='BDF', \
                               rtol=fun_rtol, atol=fun_atol)
    sol_trap = trap_solver.solve()
    print('-' * 81)

    sys.stdout.write('Integrating the original system... ')
    sys.stdout.flush()
    sol = solve_ivp_switch(boost, t_span, y0, method='BDF',
                           jac=boost.jac, rtol=fun_rtol, atol=fun_atol)
    sys.stdout.write('done.\n')

    labels = [r'$V_C$ (V)', r'$I_L$ (A)']
    fig,ax = plt.subplots(2,1,sharex=True)
    for i in range(2):
        ax[i].plot(sol['t']*1e6, sol['y'][i], 'k', lw=1)
        ax[i].plot(sol_be['t']*1e6, sol_be['y'][i], 'ro-', ms=3)
        ax[i].plot(sol_trap['t']*1e6, sol_trap['y'][i], 'go-', ms=3)
        ax[i].set_ylabel(labels[i])
    ax[1].set_xlabel(r'Time ($\mu$s)')
    ax[1].set_xlim(t_span*1e6)
    plt.show()


def envelope_var_R(use_ramp):
    T = 40e-6
    ki = 1
    Vin = 5
    Vref = 5
    C0 = 47e-6
    L0 = 10e-6
    R0 = 5

    fun_rtol = 1e-12
    fun_atol = 1e-14

    def R_fun(t):
        n_period = int(t / T)
        if n_period % 100 < 75:
            return R0
        return 2*R0

    def R_fun_sin(t):
        F = 500 # [Hz]
        dR0 = R0/10
        return R0 - dR0/2 + dR0*np.sin(2*np.pi*F*t)

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, C=C0*30, L=L0*2, \
                  R=R_fun_sin, use_compensating_ramp=use_ramp)

    t_tran = 100.1*T

    #y0 = np.array([9.3124, 1.2804])
    y0 = np.array([10.154335434351671, 1.623030961224813])

    sol = solve_ivp_switch(boost, [0,t_tran], y0, \
                           method='BDF', jac=boost.jac, \
                           rtol=fun_rtol, atol=fun_atol)
    #plt.plot(sol['t']*1e6,sol['y'][0],'k')
    #plt.plot(sol['t']*1e6,sol['y'][1],'r')
    #plt.show()

    t_span = sol['t'][-1] + np.array([0, 100*T])
    y0 = sol['y'][:,-1]
    print('t_span =', t_span)
    print('y0 =', y0)
    print('index =', boost.vector_field_index)

    print('-' * 81)
    be_solver = BEEnvelope(boost, t_span, y0, max_step=1000, \
                           T_guess=None, T=T, \
                           env_rtol=1e-2, env_atol=1e-3, \
                           solver=solve_ivp_switch, \
                           jac=boost.jac, method='BDF', \
                           rtol=fun_rtol, atol=fun_atol)
    sol_be = be_solver.solve()
    print('-' * 81)
    trap_solver = TrapEnvelope(boost, t_span, y0, max_step=1000, \
                               T_guess=None, T=T, \
                               env_rtol=1e-3, env_atol=1e-4, \
                               solver=solve_ivp_switch, \
                               jac=boost.jac, method='BDF', \
                               rtol=fun_rtol, atol=fun_atol)
    sol_trap = trap_solver.solve()
    print('-' * 81)

    sys.stdout.write('Integrating the original system... ')
    sys.stdout.flush()
    sol = solve_ivp_switch(boost, t_span, y0, method='BDF',
                           jac=boost.jac, rtol=fun_rtol, atol=fun_atol)
    sys.stdout.write('done.\n')

    labels = [r'$V_C$ (V)', r'$I_L$ (A)']
    fig,ax = plt.subplots(2,1,sharex=True)
    for i in range(2):
        ax[i].plot(sol['t']*1e6, sol['y'][i], 'k', lw=1)
        ax[i].plot(sol_be['t']*1e6, sol_be['y'][i], 'ro-', ms=3)
        ax[i].plot(sol_trap['t']*1e6, sol_trap['y'][i], 'go-', ms=3)
        ax[i].set_ylabel(labels[i])
    ax[1].set_xlabel(r'Time ($\mu$s)')
    ax[1].set_xlim(t_span*1e6)
    plt.show()


def variational_integration(use_ramp, N_periods=100, compare=False):

    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5

    def Vref_fun(t):
        if t > 1/3 and t <= 2/3:
            return Vref*0.9
        return Vref

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, clock_phase=0, use_compensating_ramp=use_ramp)

    fun_rtol = 1e-10
    fun_atol = 1e-12

    t_tran = 0*T

    if t_tran > 0:
        y0 = np.array([Vin,1])
        print('Vector field index at the beginning of the first integration: %d.' % boost.vector_field_index)
        sol = solve_ivp_switch(boost, [0,t_tran], y0, \
                           method='BDF', jac=boost.jac, \
                           rtol=fun_rtol, atol=fun_atol)
        print('Vector field index at the end of the first integration: %d.' % boost.vector_field_index)
        plt.figure()
        ax = plt.subplot(2,1,1)
        plt.plot(sol['t']*1e6,sol['y'][0],'k')
        plt.ylabel(r'$V_C$ (V)')
        plt.subplot(2,1,2,sharex=ax)
        plt.plot(sol['t']*1e6,sol['y'][1],'r')
        plt.xlabel(r'Time ($\mu$s)')
        plt.ylabel(r'$I_L$ (A)')
        plt.show()
        y0 = sol['y'][:,-1]
    else:
        y0 = np.array([8.6542,0.82007])

    T_large = N_periods*T
    boost.with_variational = True
    boost.variational_T = T_large

    t_span_var = [0,1]
    y0_var = np.concatenate((y0,np.eye(len(y0)).flatten()))

    sol = solve_ivp_switch(boost, t_span_var, y0_var, method='BDF', rtol=fun_rtol, atol=fun_atol)
    #t_events = np.sort(np.r_[sol['t_sys_events'][0], sol['t_sys_events'][1]])
    #np.savetxt('t_events_beat.txt',t_events,fmt='%14.6e')

    #np.savetxt('boost_variational.txt', pack(sol['t'],sol['y']), fmt='%.3e')

    w,v = np.linalg.eig(np.reshape(sol['y'][2:,-1],(2,2)))
    print('eigenvalues:')
    print('   ' + ' %14.5e' * boost.n_dim % tuple(w))
    print('eigenvectors:')
    for i in range(boost.n_dim):
        print('   ' + ' %14.5e' * boost.n_dim % tuple(v[i,:]))

    if compare:
        print('Loading PAN data...')
        data = np.loadtxt('DanieleTest.txt')
        t = data[:,0] - data[0,0]
        idx, = np.where(t < T_large)

    labels = [r'$V_C$ (V)', r'$I_L$ (A)']
    fig,ax = plt.subplots(3,2,sharex=True,figsize=(9,5))
    for i in range(2):
        if i == 1:
            ax[0,i].plot([sol['t'][0],sol['t'][-1]],[0,0],'r--')
        ax[0,i].plot(sol['t'],sol['y'][i],'k',lw=1)
        ax[0,i].set_ylabel(labels[i])
        ax[0,i].set_xlim([0,1])
        for j in range(2):
            k = i*2 + j
            if compare:
                ax[i+1,j].plot(t[idx]/T_large,data[idx,(k+1)*2],'r',lw=1,label='PAN')
            ax[i+1,j].plot(sol['t'],sol['y'][k+2],'k',lw=1,label='Python')
            ax[i+1,j].set_ylabel(r'$\Phi_{%d,%d}$' % (i+1,j+1))
            ax[i+1,j].set_xlim([0,1])
        ax[2,i].set_xlabel('Normalized time')
    if compare:
        ax[1,0].legend(loc='best')

    plt.savefig('boost_const_Vref.pdf')
    plt.show()

    return v

def variational_integration_var_R(use_ramp, N_periods=100, compare=False):

    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5
    C0 = 47e-6
    L0 = 10e-6
    R0 = 5

    def R_fun(t):
        n_period = int(t / T)
        if n_period % 100 < 75:
            return R0
        return 2*R0

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, C=C0*30, L=L0*2, R=R_fun, use_compensating_ramp=use_ramp)

    fun_rtol = 1e-12
    fun_atol = 1e-14

    t_tran = 0*T

    if t_tran > 0:
        y0 = np.array([Vin,1])
        print('Vector field index at the beginning of the first integration: %d.' % boost.vector_field_index)
        sol = solve_ivp_switch(boost, [0,t_tran], y0, \
                           method='BDF', jac=boost.jac, \
                           rtol=fun_rtol, atol=fun_atol)
        print('Vector field index at the end of the first integration: %d.' % boost.vector_field_index)
        plt.figure()
        ax = plt.subplot(2,1,1)
        plt.plot(sol['t']*1e6,sol['y'][0],'k')
        plt.ylabel(r'$V_C$ (V)')
        plt.subplot(2,1,2,sharex=ax)
        plt.plot(sol['t']*1e6,sol['y'][1],'r')
        plt.xlabel(r'Time ($\mu$s)')
        plt.ylabel(r'$I_L$ (A)')
        plt.show()
        y0 = sol['y'][:,-1]
    else:
        #y0 = np.array([8.6542,0.82007])
        y0 = np.array([10.154335434351671, 1.623030961224813])


    T_large = N_periods*T
    boost.with_variational = True
    boost.variational_T = T_large

    t_span_var = [0,1]
    y0_var = np.concatenate((y0,np.eye(len(y0)).flatten()))

    sol = solve_ivp_switch(boost, t_span_var, y0_var, method='BDF', rtol=fun_rtol, atol=fun_atol)
    #t_events = np.sort(np.r_[sol['t_sys_events'][0], sol['t_sys_events'][1]])
    #np.savetxt('t_events_beat.txt',t_events,fmt='%14.6e')

    #np.savetxt('boost_variational.txt', pack(sol['t'],sol['y']), fmt='%.3e')

    w,v = np.linalg.eig(np.reshape(sol['y'][2:,-1],(2,2)))
    print('eigenvalues:')
    print('   ' + ' %14.5e' * boost.n_dim % tuple(w))
    print('eigenvectors:')
    for i in range(boost.n_dim):
        print('   ' + ' %14.5e' * boost.n_dim % tuple(v[i,:]))

    if compare:
        print('Loading PAN data...')
        data = np.loadtxt('DanieleTest.txt')
        t = data[:,0] - data[0,0]
        idx, = np.where(t < T_large)

    labels = [r'$V_C$ (V)', r'$I_L$ (A)']
    fig,ax = plt.subplots(3,2,sharex=True,figsize=(9,5))
    for i in range(2):
        if i == 1:
            ax[0,i].plot([sol['t'][0],sol['t'][-1]],[0,0],'r--')
        ax[0,i].plot(sol['t'],sol['y'][i],'k',lw=1)
        ax[0,i].set_ylabel(labels[i])
        ax[0,i].set_xlim([0,1])
        for j in range(2):
            k = i*2 + j
            if compare:
                ax[i+1,j].plot(t[idx]/T_large,data[idx,(k+1)*2],'r',lw=1,label='PAN')
            ax[i+1,j].plot(sol['t'],sol['y'][k+2],'k',lw=1,label='Python')
            ax[i+1,j].set_ylabel(r'$\Phi_{%d,%d}$' % (i+1,j+1))
            ax[i+1,j].set_xlim([0,1])
        ax[2,i].set_xlabel('Normalized time')
    if compare:
        ax[1,0].legend(loc='best')

    #plt.savefig('boost_const_Vref.pdf')
    plt.show()

    return v


def variational_envelope(use_ramp, N_periods=100, eig_vect=None, compare=False):
    if compare and eig_vect is None:
        print('You must provide the initial eigenvectors if compare is set to True.')
        return

    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, clock_phase=0, use_compensating_ramp=use_ramp)

    fun_rtol = 1e-10
    fun_atol = 1e-12

    t_tran = 50*T

    if t_tran > 0:
        print('Vector field index at the beginning of the first integration: %d.' % boost.vector_field_index)
        sol = solve_ivp_switch(boost, [0,t_tran], np.array([Vin,1]), \
                               method='BDF', jac=boost.jac, \
                               rtol=fun_rtol, atol=fun_atol)
        y0 = sol['y'][:,-1]
        print('Vector field index at the end of the first integration: %d.' % boost.vector_field_index)
        plt.figure()
        ax = plt.subplot(2,1,1)
        plt.plot(sol['t']*1e6,sol['y'][0],'k')
        plt.ylabel(r'$V_C$ (V)')
        plt.subplot(2,1,2,sharex=ax)
        plt.plot(sol['t']*1e6,sol['y'][1],'r')
        plt.xlabel(r'Time ($\mu$s)')
        plt.ylabel(r'$I_L$ (A)')
        plt.show()
    else:
        y0 = np.array([8.6542,0.82007])

    T_large = N_periods*T
    T_small = T
    boost.with_variational = True
    boost.variational_T = T_large

    t_span_var = [0,1]
    y0_var = np.concatenate((y0,np.eye(len(y0)).flatten()))

    sol = solve_ivp_switch(boost, t_span_var, y0_var, method='BDF', rtol=fun_rtol, atol=fun_atol)

    rtol = 1e-1
    atol = 1e-2
    be_var_solver = BEEnvelope(boost, [0,T_large], y0, T_guess=None, T=T_small, \
                               env_rtol=rtol, env_atol=atol, max_step=1000,
                               is_variational=True, T_var_guess=None, T_var=None, \
                               var_rtol=rtol, var_atol=atol, solver=solve_ivp_switch, \
                               rtol=fun_rtol, atol=fun_atol, method='BDF')
    trap_var_solver = TrapEnvelope(boost, [0,T_large], y0, T_guess=None, T=T_small, \
                                   env_rtol=rtol, env_atol=atol, max_step=1000,
                                   is_variational=True, T_var_guess=None, T_var=None, \
                                   var_rtol=rtol, var_atol=atol, solver=solve_ivp_switch, \
                                   rtol=fun_rtol, atol=fun_atol, method='BDF')
    print('-' * 100)
    var_sol_be = be_var_solver.solve()
    print('-' * 100)
    var_sol_trap = trap_var_solver.solve()
    print('-' * 100)

    eig,_ = np.linalg.eig(np.reshape(sol['y'][2:,-1],(2,2)))
    print('         correct eigenvalues:', eig)
    eig,_ = np.linalg.eig(np.reshape(var_sol_be['y'][2:,-1],(2,2)))
    print('  BE approximate eigenvalues:', eig)
    eig,_ = np.linalg.eig(np.reshape(var_sol_trap['y'][2:,-1],(2,2)))
    print('TRAP approximate eigenvalues:', eig)

    if compare:
        data = np.loadtxt('EigFuncDaniele.txt')
        t = (data[:,0] - T_large) / T_large

        n_steps = len(var_sol_be['M'])
        y = np.zeros((boost.n_dim**2,n_steps+1))
        y[:,0] = eig_vect.flatten()
        for i,mat in enumerate(var_sol_be['M']):
            y[:,i+1] = (mat @ np.reshape(y[:,i],(boost.n_dim,boost.n_dim))).flatten()

        fig,ax = plt.subplots(boost.n_dim,boost.n_dim,sharex=True)
        ax[0,0].plot(t, data[:,1], 'k.-')
        ax[0,0].plot(var_sol_be['t'], y[0,:], 'ro')
        ax[0,1].plot(t, data[:,3], 'k.-')
        ax[0,1].plot(var_sol_be['t'], y[1,:], 'ro')
        ax[1,0].plot(t, data[:,2], 'k.-')
        ax[1,0].plot(var_sol_be['t'], y[2,:], 'ro')
        ax[1,1].plot(t, data[:,4], 'k.-')
        ax[1,1].plot(var_sol_be['t'], y[3,:], 'ro')
        for i in range(2):
            for j in range(2):
                ax[i,j].set_xlim([0,1])
                ax[i,j].set_ylim([-1,1])

    labels = [r'$V_C$ (V)', r'$I_L$ (A)']
    fig,ax = plt.subplots(3,2,sharex=True)
    for i in range(2):
        ax[0,i].plot(sol['t'],sol['y'][i],'k',lw=1)
        ax[0,i].plot(var_sol_be['t'],var_sol_be['y'][i],'rs-',ms=3)
        ax[0,i].plot(var_sol_trap['t'],var_sol_trap['y'][i],'go-',ms=3)
        ax[0,i].set_ylabel(labels[i])
        ax[0,i].set_xlim([0,1])
        for j in range(2):
            k = i*2 + j
            ax[i+1,j].plot(sol['t'],sol['y'][k+2],'k',lw=1)
            ax[i+1,j].set_ylabel(r'$\Phi_{%d,%d}$' % (i+1,j+1))
            ax[i+1,j].plot(var_sol_be['t'],var_sol_be['y'][k+2],'rs',ms=3)
            ax[i+1,j].plot(var_sol_trap['t'],var_sol_trap['y'][k+2],'go',ms=3)
            ax[i+1,j].set_xlim([0,1])
        ax[2,i].set_xlabel('Normalized time')

    plt.show()


def shooting(use_ramp):

    T = 20e-6
    ki = 1
    Vin = 5
    Vref = 5

    boost = Boost(0, T=T, ki=ki, Vin=Vin, Vref=Vref, clock_phase=0, use_compensating_ramp=use_ramp)

    fun_rtol = 1e-10
    fun_atol = 1e-12

    y0_guess = np.array([Vin,0])

    t_tran = 0.1*T

    if t_tran > 0:
        tran = solve_ivp_switch(boost, [0,t_tran], y0_guess, method='BDF', \
                                jac=boost.jac, rtol=fun_rtol, atol=fun_atol)
        fig,(ax1,ax2) = plt.subplots(2,1,sharex=True)
        ax1.plot(tran['t']/T,tran['y'][0],'k')
        ax1.set_ylabel(r'$V_C$ (V)')
        ax2.plot(tran['t']/T,tran['y'][1],'k')
        ax2.set_xlabel('No. of periods')
        ax2.set_ylabel(r'$I_L$ (A)')
        plt.show()

    T_large = 5*T
    T_small = T

    estimate_T = False

    shoot = EnvelopeShooting(boost, T_large, estimate_T, T_small, \
                             tol=1e-3, env_solver=BEEnvelope, \
                             env_rtol=1e-2, env_atol=1e-3, \
                             var_rtol=1e-1, var_atol=1e-2, \
                             fun_solver=solve_ivp_switch, \
                             rtol=fun_rtol, atol=fun_atol, \
                             method='BDF', jac=boost.jac)
    sol_shoot = shoot.run(y0_guess)
    print('Number of iterations: %d.' % sol_shoot['n_iter'])

    t_span_var = [0,1]
    boost.with_variational = True
    boost.variational_T = T_large

    col = 'krgbcmy'
    lw = 0.8
    fig,ax = plt.subplots(3,2,sharex=True,figsize=(12,7))

    for i,integr in enumerate(sol_shoot['integrations']):

        y0 = integr['y'][:2,0]
        y0_var = np.concatenate((y0,np.eye(2).flatten()))
        sol = solve_ivp_switch(boost, t_span_var, y0_var, method='BDF', rtol=fun_rtol, atol=fun_atol)

        for j in range(2):
            ax[0,j].plot(sol['t'],sol['y'][j],col[i],lw=lw,label='Iter #%d' % (i+1))
            ax[0,j].plot(integr['t'],integr['y'][j],col[i]+'o-',lw=1,ms=3)
            for k in range(2):
                n = j*2 + k
                ax[j+1,k].plot(sol['t'],sol['y'][n+2],col[i],lw=lw)
                ax[j+1,k].plot(integr['t'],integr['y'][n+2],col[i]+'o-',lw=1,ms=3)
                ax[j+1,k].set_ylabel(r'$\Phi_{%d,%d}$' % (j+1,k+1))
                ax[j+1,k].set_xlim([0,1])
            ax[2,j].set_xlabel('Normalized time')
    ax[0,0].legend(loc='best')
    ax[0,0].set_ylabel(r'$V_C$ (V)')
    ax[0,1].set_ylabel(r'$I_L$ (A)')
    plt.savefig('boost_shooting.pdf')
    plt.show()


def eig_comparison(use_ramp):
    eig = variational_integration(use_ramp, N_periods=1, compare=False)
    variational_envelope(use_ramp, N_periods=100, eig_vect=eig, compare=True)


cmds = {'system': system, 'system-var-R': system_var_R, 'envelope': envelope, \
        'envelope-var-R': envelope_var_R, 'variational-envelope': variational_envelope, \
        'shooting': shooting, 'eig': eig_comparison, \
        'variational-integration': variational_integration, \
        'variational-integration-var-R': variational_integration_var_R}


cmd_descriptions = {'system': 'integrate the boost dynamical system', \
                    'system-var-R': 'integrate the boost dynamical system with varying load resistance', \
                    'envelope': 'compute the envelope of the boost', \
                    'envelope-var-R': 'compute the envelope of the boost with varying load resistance', \
                    'variational-envelope': 'compute the envelope of the boost with variational part', \
                    'shooting': 'perform a shooting analysis of the boost', \
                    'eig': 'compare eigenvalues obtained with full and envelope variational systems', \
                    'variational-integration': 'integrate the boost and its variational part', \
                    'variational-integration-var-R': 'integrate the boost with varying load and its variational part'}


def list_commands():
    print('\nThe following are accepted commands:')
    nch = 0
    for cmd in cmds:
        if len(cmd) > nch:
            nch = len(cmd)
    fmt = '\t{:<%ds} {}' % (nch + 5)
    for i,cmd in enumerate(cmds):
        print(fmt.format(cmd,cmd_descriptions[cmd]))


def usage():
    print('usage: {} [--use-ramp] command'.format(progname))
    list_commands()


if __name__ == '__main__':

    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    if sys.argv[1] in ('-h', '--help', 'help'):
        usage()
        sys.exit(0)

    if sys.argv[1] == '--use-ramp':
        use_ramp = True
        if len(sys.argv) != 3:
            usage()
            sys.exit(1)
        cmd = sys.argv[2]
    else:
        use_ramp = False
        cmd = sys.argv[1]

    if not cmd in cmds:
        print('{}: {}: unknown command.'.format(progname, cmd))
        list_commands()
        sys.exit(1)

    cmds[cmd](use_ramp)


