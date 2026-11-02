"""Build any sdn_core topology in Mininet with the SAME port numbers the controllers assume."""
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink

from sdn_core import TOPOLOGIES, edges_of


def build_net(name, controller_port=6633):
    topo = TOPOLOGIES[name]()
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=False, build=False)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=controller_port)
    for d in sorted(topo.adj):
        net.addSwitch('s%d' % d, dpid='%016x' % d, protocols='OpenFlow13')
    for i, (h, (mac, sw, port)) in enumerate(sorted(topo.hosts.items()), start=1):
        net.addHost(h, mac=mac, ip='10.0.0.%d/24' % i)
        net.addLink(h, 's%d' % sw, port1=0, port2=port, bw=10, delay='2ms')
    for u, v in edges_of(topo):
        net.addLink('s%d' % u, 's%d' % v, port1=topo.ports[u][v], port2=topo.ports[v][u], bw=10, delay='2ms')
    return net, topo
