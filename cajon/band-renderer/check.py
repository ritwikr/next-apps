import sys, numpy as np
from scipy.io import wavfile
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
k=sys.argv[1]
sr,x=wavfile.read(f'out/{k}_loop.wav'); x=x.astype(float)/32767
d=np.abs(np.diff(x,axis=0)); seam=np.abs(x[0]-x[-1])
print(k,'seam jump',seam.round(4),'p99 step',np.percentile(d,99,axis=0).round(4),'max step',d.max(0).round(3))
# spectrum balance (octave bands)
m=x.mean(1); F=np.abs(np.fft.rfft(m))**2; f=np.fft.rfftfreq(len(m),1/sr)
bands=[31,63,125,250,500,1000,2000,4000,8000,16000]
print(' '.join(f'{b}:{10*np.log10(F[(f>=b/1.41)&(f<b*1.41)].sum()+1e-9):.0f}' for b in bands))
print('L/R corr', np.corrcoef(x[:,0],x[:,1])[0,1].round(2))
fig,ax=plt.subplots(2,1,figsize=(14,7))
ax[0].specgram(m,NFFT=4096,Fs=sr,noverlap=2048,cmap='magma',vmin=-120); ax[0].set_ylim(0,6000)
t=np.arange(len(m))/sr; ax[1].plot(t[::200],m[::200],lw=.3)
plt.tight_layout(); plt.savefig(f'out/{k}.png',dpi=70)
