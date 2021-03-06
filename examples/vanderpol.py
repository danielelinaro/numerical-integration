
import numpy as np
from scipy.integrate import solve_ivp
import matplotlib.pyplot as plt

from polimi.systems import VanderPol
from polimi.envelope import BEEnvelope, TrapEnvelope


def system():
    epsilon = 1e-3
    A = [10,1]
    T = [4,400]

    t0 = 0
    t_end = np.max(T)
    t_span = np.array([t0, t_end])

    y0 = np.array([-2,1])

    fun_rtol = 1e-10
    fun_atol = 1e-12

    vdp = VanderPol(epsilon, A, T)

    sol = solve_ivp(vdp, t_span, y0, method='BDF', \
                    jac=vdp.jac, rtol=fun_rtol, atol=fun_atol)

    ax = plt.subplot(2, 1, 1)
    plt.plot(sol['t'], sol['y'][0], 'k')
    plt.ylabel(r'$V_C$ (V)')
    plt.subplot(2, 1, 2, sharex=ax)
    plt.plot(sol['t'], sol['y'][1], 'k')
    plt.xlabel('Time (s)')
    plt.ylabel(r'$I_L$ (A)')
    plt.show()


def envelope():
    epsilon = 1e-3
    A = [10,1]
    T = [4,400]

    vdp = VanderPol(epsilon, A, T)
    fun_rtol = 1e-10
    fun_atol = 1e-12

    t_tran = 0

    if t_tran > 0:
        sol = solve_ivp(vdp, [0, t_tran], [-2,1], method='BDF', \
                        jac=vdp.jac, rtol=fun_rtol, atol=fun_atol)
        y0 = sol['y'][:,-1]
    else:
        y0 = np.array([-5.84170838, 0.1623759])

    print('y0 =', y0)

    t0 = 0
    t_end = np.max(T)
    t_span = np.array([t0, t_end])

    env_rtol = 1e-1
    env_atol = 1e-2
    be_env_solver = BEEnvelope(vdp, t_span, y0, T=np.min(T), \
                               env_rtol=env_rtol, env_atol=env_atol, \
                               rtol=fun_rtol, atol=fun_atol, \
                               method='BDF', jac=vdp.jac)
    be_env_sol = be_env_solver.solve()

    trap_env_solver = TrapEnvelope(vdp, t_span, y0, T=np.min(T), \
                                   env_rtol=env_rtol, env_atol=env_atol, \
                                   rtol=fun_rtol, atol=fun_atol, \
                                   method='BDF', jac=vdp.jac)
    trap_env_sol = trap_env_solver.solve()

    sol = solve_ivp(vdp, t_span, y0, method='BDF', \
                    jac=vdp.jac, rtol=fun_rtol, atol=fun_atol)

    fig,(ax1,ax2) = plt.subplots(2, 1, sharex=True)
    ax1.plot(sol['t'], sol['y'][0], 'k')
    ax1.plot(be_env_sol['t'], be_env_sol['y'][0], 'ro-')
    ax1.plot(trap_env_sol['t'], trap_env_sol['y'][0], 'gs-')
    ax1.set_ylabel(r'$V_C$ (V)')
    ax2.plot(sol['t'], sol['y'][1], 'k')
    ax2.plot(be_env_sol['t'], be_env_sol['y'][1], 'ro-')
    ax2.plot(trap_env_sol['t'], trap_env_sol['y'][1], 'gs-')
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel(r'$I_L$ (A)')
    plt.show()


def variational_envelope():
    epsilon = 1e-3
    A = [10,1]
    T = [4,200]
    T_large = max(T)
    T_small = min(T)
    T_small_guess = min(T) * 0.95

    vdp = VanderPol(epsilon, A, T)

    t_span_var = [0,1]
    if A[0] == 10:
        y0 = np.array([-5.8133754, 0.13476983])
    elif A[0] == 1:
        y0 = np.array([9.32886314, 0.109778919])
    y0_var = np.concatenate((y0,np.eye(len(y0)).flatten()))

    vdp.with_variational = True
    vdp.variational_T = T_large
    sol = solve_ivp(vdp, t_span_var, y0_var, rtol=1e-8, atol=1e-10, dense_output=True)

    rtol = 1e-1
    atol = 1e-2
    be_var_solver = BEEnvelope(vdp, [0,T_large], y0, T_guess=None, T=T_small, \
                               env_rtol=rtol, env_atol=atol, is_variational=True, \
                               T_var_guess=2*np.pi*0.95, var_rtol=rtol, var_atol=atol,
                               solver=solve_ivp, rtol=1e-8, atol=1e-10)
    trap_var_solver = TrapEnvelope(vdp, [0,T_large], y0, T_guess=None, T=T_small, \
                                   env_rtol=rtol, env_atol=atol, is_variational=True, \
                                   T_var_guess=2*np.pi*0.95, var_rtol=rtol, var_atol=atol,
                                   solver=solve_ivp, rtol=1e-8, atol=1e-10)
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

    light_gray = [.6,.6,.6]
    dark_gray = [.3,.3,.3]
    black = [0,0,0]
    fig,(ax1,ax2) = plt.subplots(2,1,sharex=True,figsize=(3,3.5))
    ax1.plot(sol['t'],sol['y'][0],color=light_gray,lw=1)
    ax1.plot(var_sol_be['t'],var_sol_be['y'][0],'o-',lw=1,\
             color=black,markerfacecolor='w',markersize=4)
    #ax1.plot(var_sol_trap['t'],var_sol_trap['y'][0],'s',lw=1,\
    #         color=light_gray,markerfacecolor='w',markersize=4)
    ax1.set_ylabel('x')
    ax1.set_xlim([0,1])
    ax1.set_ylim([-9,9])
    ax1.set_yticks(np.arange(-9,10,3))
    #ax2.plot(t_span_var,[0,0],'b')
    ax2.plot(sol['t'],sol['y'][2],color=light_gray,lw=1,label='Full solution')
    ax2.plot(var_sol_be['t'],var_sol_be['y'][2],'o',lw=1,\
             color=black,markerfacecolor='w',markersize=4)
    for i in range(0,len(var_sol_be['var']['t'])-3,3):
        if i == 0:
            ax2.plot(var_sol_be['var']['t'][i:i+3],var_sol_be['var']['y'][0,i:i+3],'o-',\
                     color=black,linewidth=1,markerfacecolor='w',markersize=4,\
                     label='Envelope')
        else:
            ax2.plot(var_sol_be['var']['t'][i:i+3],var_sol_be['var']['y'][0,i:i+3],'o-',\
                     color=black,linewidth=1,markerfacecolor='w',markersize=4)
    ax2.legend(loc='best')
    #ax2.plot(var_sol_trap['t'],var_sol_trap['y'][2],'s',lw=1,\
    #         color=light_gray,markerfacecolor='w',markersize=4)
    #for i in range(0,len(var_sol_trap['var']['t']),3):
    #    ax2.plot(var_sol_trap['var']['t'][i:i+3],var_sol_trap['var']['y'][0,i:i+3],'.-',\
    #             color=[1,0,1])
    ax2.set_xlabel('Normalized time')
    ax2.set_ylabel(r'$\Phi_{1,1}$')
    ax2.set_xlim([0,1])
    ax2.set_ylim([-1.2,1.2])
    ax2.set_yticks(np.arange(-1,1.5,0.5))
    plt.savefig('vanderpol_variational.pdf')
    plt.show()


if __name__ == '__main__':
    import polimi.utils
    polimi.utils.set_rc_defaults()
    #system()
    #envelope()
    variational_envelope()
