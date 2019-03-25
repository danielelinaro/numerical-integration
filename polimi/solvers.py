
import numpy as np

def forward_euler(fun, t_span, y0, h):
    n_dim = len(y0)
    t = np.arange(t_span[0],t_span[1],h)
    n_steps = len(t)
    y = np.zeros((n_dim,n_steps))
    y[:,0] = y0
    for i in range(1,n_steps):
        y[:,i] = y[:,i-1] + h*fun(t[i-1],y[:,i-1])
    return {'t': t, 'y': y}

def backward_euler(fun, t_span, y0, h):
    from scipy.optimize import fsolve
    n_dim = len(y0)
    t = np.arange(t_span[0],t_span[1],h)
    n_steps = len(t)
    y = np.zeros((n_dim,n_steps))
    y[:,0] = y0
    for i in range(1,n_steps):
        y[:,i] = fsolve(lambda Y: Y-y[:,i-1]-h*fun(t[i],Y), y[:,i-1])
    return {'t': t, 'y': y}

def bdf(fun, t_span, y0, h, order):

    if order <= 0 or order > 6:
        raise Exception('order must be a value between 1 and 6')
    
    A = np.zeros((6,6))
    B = np.zeros((6,6))
    Bstar = np.zeros((6,6))
    A[:,0] = 1.
    B[0,0] = 1.
    B[1,:2] = np.array([3.,-1.])/2.
    B[2,:3] = np.array([23.,-16.,5.])/12.
    B[3,:4] = np.array([55.,-59.,37.,-9.])/24.
    B[4,:5] = np.array([1901.,-2774.,2616.,-1274.,251.])/720.
    B[5,:6] = np.array([4277.,-7923.,9982.,-7298.,2877.,-475.])/1440.
    Bstar[0,0] = 1.
    Bstar[1,:2] = np.array([1.,1.])/2.
    Bstar[2,:3] = np.array([5.,8.,-1.])/12.
    Bstar[3,:4] = np.array([9.,19.,-5.,1.])/24.
    Bstar[4,:5] = np.array([251.,646.,-264.,106.,-19.])/720.
    Bstar[5,:6] = np.array([475.,1427.,-798.,482.,-173.,27.])/1440.

    n_dim = len(y0)
    t = np.arange(t_span[0],t_span[1],h)
    n_steps = len(t)
    y = np.zeros((n_dim,n_steps))
    dydt = np.zeros((n_dim,n_steps))
    y[:,0] = y0
    dydt[:,0] = fun(t[0],y[:,0])
    
    for i in range(1,order):
        k1 = fun(t[i-1],y[:,i-1])
        k2 = fun(t[i-1],y[:,i-1]+h/2*k1)
        k3 = fun(t[i-1],y[:,i-1]+h/2*k2)
        k4 = fun(t[i-1],y[:,i-1]+h*k3)
        y[:,i] = y[:,i-1] + h*(k1+2*k2+2*k3+k4)/6.
        dydt[:,i] = fun(t[i],y[:,i])
        
    for i in range(order,n_steps):
        ### predictor ###
        y_p = np.zeros(n_dim)
        for j in range(order):
            y_p += A[order-1,j]*y[:,i-1-j] + h*B[order-1,j]*dydt[:,i-1-j]
        ### corrector ###
        y_c = A[order-1,0]*y[:,i-1] + h*Bstar[order-1,0]*fun(t[i],y_p)
        for j in range(1,order):
            y_c += A[order-1,j]*y[:,i-j] + h*Bstar[order-1,j]*dydt[:,i-j]
        y[:,i] = y_c
        dydt[:,i] = fun(t[i],y[:,i])
    
    return {'t': t, 'y': y}

def vanderpol():
    from systems import vdp
    import matplotlib.pyplot as plt
    from scipy.integrate import solve_ivp
    A = [0]
    T = [1]
    epsilon = 1e-3
    y0 = [2e-3,0]
    tend = 1000
    h = 0.05
    fun = lambda t,y: vdp(t,y,epsilon,A,T)
    sol = solve_ivp(fun, [0,tend], y0, method='RK45', rtol=1e-6, atol=1e-8)
    print(np.mean(np.diff(sol['t'])))
    sol_fw = forward_euler(fun, [0,tend], y0, h/5)
    sol_bw = backward_euler(fun, [0,tend], y0, h/5)
    sol_bdf = bdf(fun, [0,tend], y0, h, order=3)
    plt.plot(sol['t'],sol['y'][0],'k',label='solve_ivp')
    plt.plot(sol_fw['t'],sol_fw['y'][0],'b',label='FW')
    plt.plot(sol_bw['t'],sol_bw['y'][0],'r',label='BW')
    plt.plot(sol_bdf['t'],sol_bdf['y'][0],'m',label='BDF')
    plt.legend(loc='best')
    plt.show()

def main():
    import matplotlib.pyplot as plt
    equil = True
    if equil:
        l = -1
        fun = lambda t,y: l*y
        sol = lambda t: np.exp(l*t)
        y0 = np.array([1])
        tend = 10
        h = 0.05
    else:
        f = 1
        fun = lambda t,y: 2 * np.pi * f * np.cos(2 * np.pi * f * t)
        sol = lambda t: np.sin(2 * np.pi * f * t)
        y0 = np.array([0])
        tend = 5./f
        h = 0.001
    sol_fw = forward_euler(fun, [0,tend], y0, h)
    sol_bw = backward_euler(fun, [0,tend], y0, h)
    sol_bdf = bdf(fun, [0,tend], y0, 2*h, order=3)
    t = np.linspace(0,tend,1000)
    plt.plot(t,sol(t),'k',label='Solution')
    plt.plot(sol_fw['t'],sol_fw['y'][0],'b',label='FW')
    plt.plot(sol_bw['t'],sol_bw['y'][0],'r',label='BW')
    plt.plot(sol_bdf['t'],sol_bdf['y'][0],'m',label='BDF')
    plt.legend(loc='best')
    plt.show()

if __name__ == '__main__':
    main()
    #vanderpol()
