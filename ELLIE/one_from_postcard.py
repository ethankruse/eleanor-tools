import os, sys
import numpy as np
import matplotlib.pyplot as plt
from lightkurve  import KeplerTargetPixelFile as ktpf
from astropy.io  import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u
from scipy       import ndimage
from ellie  import find_sources as fs
from ellie import data_products as dp
from astropy.table import Table
from astropy.nddata import Cutout2D
from time import strftime

def find_postcard(id, pos):
    """ Uses postcard_catalog to find where the source is """
    t = Table.read('postcard.cat', format='ascii.basic')

    # Corrects position with pointing model
    pm = np.loadtxt('pointingModel_3-3.txt', skiprows=1, usecols=(1,2,3))
    initShift = pm[0]
    initShift[0] = np.radians(initShift[0])

    in_file=[None]
    for i in range(len(t)):
        data=[]
        for j in range(146):
            data.append(t[i][j])
        d = dict(zip(t.colnames[0:146], data))
        hdr = fits.Header(cards=d)
        xy = WCS(hdr).all_world2pix(pos[0], pos[1], 1)

        x = xy[0]*np.cos(initShift[0]) - xy[1]*np.sin(initShift[0]) - initShift[1]
        y = xy[0]*np.sin(initShift[0]) + xy[1]*np.cos(initShift[0]) - initShift[2]

        x_cen, y_cen, l, w = t['POST_CENX'][i], t['POST_CENY'][i], t['POST_SIZE1'][i]/2., t['POST_SIZE2'][i]/2.
       # Checks to see if xy coordinates of source falls in postcard
        if (xy[0] >= x_cen-l) & (xy[0] <= x_cen+l) & (xy[1] >= y_cen-w) & (xy[1] <= y_cen+w):
            if in_file[0]==None:
                in_file[0]=i
            else:
                in_file.append(i)
            # If more than one postcard is found, choose the one where the source is closer to the center
            if len(in_file) > 1:
                dist1 = np.sqrt( (xy[0]-t['POST_CENX'][in_files[0]])**2 + (xy[1]-t['POST_CENY'][in_files[0]])**2  )
                dist2 = np.sqrt( (xy[0]-t['POST_CENX'][in_files[1]])**2 + (xy[1]-t['POST_CENY'][in_files[1]])**2  )
                if dist1 >= dist2:
                    in_file=[in_file[1]]
                else:
                    in_file=[in_file[0]]
    # Returns postcard filename, postcard header, xy coordinates of source
    print(t['POST_CENX'][in_file[0]], t['POST_CENY'][in_file[0]])
    return t['POST_FILE'][in_file[0]], t[in_file[0]]
            
def init_shift(xy, camera, chip):
    initShift = np.loadtxt('pointingModel_{}-{}.txt'.format(camera, chip), skiprows=1,
                           usecols=(1,2,3))[0]
    initShift[0] = np.radians(initShift[0])
    x = xy[0]*np.cos(initShift[0]) - xy[1]*np.sin(initShift[0]) - initShift[1]
    y = xy[0]*np.sin(initShift[0]) + xy[1]*np.cos(initShift[0]) - initShift[2]
    return [x, y]


def from_class(id, mission):
    """ Gets crossmatching information & position of source """
    if mission == 'tic':
        locate = fs(tic=id)
        tic_id, pos, tmag = locate.tic_pos_by_ID()
        locate = fs(tic=id, pos=pos)
        table  = locate.find_by_position()
    elif mission == 'gaia':
        locate = fs(gaia=id)
        table  = locate.gaia_pos_by_ID()
        pos = [table['ra'].data[0], table['dec'].data[0]]
        locate = fs(gaia=id, pos=pos)
        table  = locate.find_by_position()
    else:
        print("Unknown mission. Please try again.")
        return
    return table



def main(id, mission):
    source_info = from_class(id, mission)
    pos = [source_info['RA'].data[0], source_info['Dec'].data[0]]
    
    lcClass = dp(id=id, camera=3, chip=3, sector=1)

    postcard, card_info = find_postcard(id, pos)

    data = []
    for i in range(147):
        data.append(card_info[i])
    d = dict(zip(card_info.colnames[0:146], data))
    hdr = fits.Header(cards=d)
    xy = WCS(hdr).all_world2pix(pos[0], pos[1], 1)

    # Corrects position with pointing model                                  
    pm = np.loadtxt('pointingModel_3-3.txt', skiprows=1, usecols=(1,2,3))
    initShift = pm[0]
    initShift[0] = np.radians(initShift[0])
    x = xy[0]*np.cos(initShift[0]) - xy[1]*np.sin(initShift[0]) - initShift[1]
    y = xy[0]*np.sin(initShift[0]) + xy[1]*np.cos(initShift[0]) - initShift[2]

    post_fits = ktpf.from_fits(postcard)

    # Extracts camera & chip from postcard name
    camera, chip = postcard[11:12], postcard[13:14]
    xy = init_shift(xy, camera, chip)
    delY, delX = xy[0]-card_info['POST_CENX'], xy[1]-card_info['POST_CENY']

    newX, newY = card_info['POST_SIZE1']/2. + delX, card_info['POST_SIZE2']/2. + delY

    newX, newY = int(np.ceil(newX)), int(np.ceil(newY))
    tpf = post_fits.flux[:,newX-4:newX+5, newY-4:newY+5]

    plt.imshow(tpf[0], origin='lower')#, vmin=50, vmax=200)
    plt.show()
    print(len(tpf))
    #### LC CORRECTION IN ellie.py NOT WORKING ####
    radius, shape, lc, uncorrLC = lcClass.aperture_fitting(tpf=tpf)

    plt.plot(np.arange(0,len(tpf),1), lc, 'r')
    plt.plot(np.arange(0,len(tpf),1), uncorrLC, 'k')
    plt.show()
    lcData = [np.arange(0,len(tpf),1), np.array(uncorrLC), np.array(lc)]
    
    ## ADD HEADER THINGS (version, date created, github, author, fun asterisks
    hdr.append(('COMMENT', '***********************'))
    hdr.append(('COMMENT', '*     ELLIE INFO      *'))
    hdr.append(('COMMENT', '***********************'))
    hdr.append(('AUTHOR' , 'Adina D. Feinstein'))
    hdr.append(('VERSION', '1.0'))
    hdr.append(('GITHUB' , 'https://github.com/afeinstein20/ELLIE'))
    hdr.append(('CREATED', strftime('%Y-%m-%d'),
                'ELLIE file creation date (YYY-MM-DD)'))


    hdu1 = fits.PrimaryHDU(header=hdr)
    hdu2 = fits.ImageHDU()
    hdu1.data = tpf
    hdu2.data = lcData
    new_hdu = fits.HDUList([hdu1, hdu2])
    
    new_hdu.writeto('test.fits')

#main(219870537, 'tic')
#main(229669377, 'tic')
#main(420888018, 'tic')
main(198593129, 'tic')
